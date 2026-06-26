"""测试检索器"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parsers.base_parser import Document as ParsedDocument
from src.retrievers.rag_retriever import (
    VectorRetriever,
    BM25Retriever,
    HybridRetriever,
    SearchConfig,
)
from src.retrievers.pipeline import PipelineConfig, SecondBrainPipeline


@pytest.fixture
def sample_docs():
    return [
        Document(page_content="Python 是一种通用编程语言，支持面向对象和函数式编程。", metadata={"title": "Python介绍", "domain": "编程", "relative_path": "py.md", "content_hash": "h1"}),
        Document(page_content="机器学习是人工智能的一个分支，通过数据训练模型。", metadata={"title": "ML介绍", "domain": "AI/ML", "relative_path": "ml.md", "content_hash": "h2"}),
        Document(page_content="Java 是一种面向对象的编程语言，广泛用于企业级开发。", metadata={"title": "Java介绍", "domain": "编程", "relative_path": "java.md", "content_hash": "h3"}),
        Document(page_content="深度学习使用多层神经网络来学习数据的层次表示。", metadata={"title": "DL介绍", "domain": "AI/ML", "relative_path": "dl.md", "content_hash": "h4"}),
        Document(page_content="Git 是分布式版本控制系统，用于跟踪代码变更。", metadata={"title": "Git介绍", "domain": "编程", "relative_path": "git.md", "content_hash": "h5"}),
    ]


class TestBM25Retriever:
    def test_build_and_search(self, sample_docs):
        retriever = BM25Retriever()
        retriever.build_index(sample_docs)
        results = retriever.search("编程语言", top_k=3)
        assert len(results) <= 3
        assert all(isinstance(doc, Document) for doc, score in results)

    def test_domain_filter(self, sample_docs):
        retriever = BM25Retriever()
        retriever.build_index(sample_docs)
        results = retriever.search("编程", top_k=10, domain="AI/ML")
        for doc, _ in results:
            assert doc.metadata["domain"] == "AI/ML"

    def test_add_and_remove_documents(self, sample_docs):
        retriever = BM25Retriever()
        retriever.build_index(sample_docs[:3])
        assert len(retriever.documents) == 3

        retriever.add_documents(sample_docs[3:])
        assert len(retriever.documents) == 5
        assert retriever.bm25 is not None

        removed = retriever.remove_documents_by_relative_paths({"py.md", "java.md"})
        assert removed == 2
        assert len(retriever.documents) == 3
        remaining_paths = {d.metadata["relative_path"] for d in retriever.documents}
        assert remaining_paths == {"ml.md", "dl.md", "git.md"}


class TestVectorRetriever:
    def test_build_and_search(self, sample_docs):
        retriever = VectorRetriever(embedding_dim=768)
        retriever.build_index(sample_docs)
        assert retriever.index.ntotal == 5
        results = retriever.search("编程语言", top_k=3)
        assert len(results) <= 3
        assert all(isinstance(doc, Document) for doc, score in results)

    def test_save_and_load(self, sample_docs, tmp_path):
        retriever = VectorRetriever(embedding_dim=768)
        retriever.build_index(sample_docs)
        retriever.save(str(tmp_path))

        loaded = VectorRetriever()
        loaded.load(str(tmp_path))
        assert loaded.index.ntotal == 5
        results = loaded.search("编程", top_k=2)
        assert len(results) <= 2

    def test_add_documents(self, sample_docs):
        retriever = VectorRetriever(embedding_dim=768)
        retriever.build_index(sample_docs[:3])
        assert retriever.index.ntotal == 3

        retriever.add_documents(sample_docs[3:])
        assert retriever.index.ntotal == 5
        results = retriever.search("神经网络", top_k=2)
        assert len(results) <= 2

    def test_remove_documents_by_relative_paths(self, sample_docs):
        retriever = VectorRetriever(embedding_dim=768)
        retriever.build_index(sample_docs)
        assert retriever.index.ntotal == 5

        removed = retriever.remove_documents_by_relative_paths({"py.md", "java.md"})
        assert removed == 2
        assert retriever.index.ntotal == 3
        remaining_paths = {d.metadata["relative_path"] for d in retriever.documents}
        assert remaining_paths == {"ml.md", "dl.md", "git.md"}

        # 删除不存在的路径不应影响
        removed2 = retriever.remove_documents_by_relative_paths({"not_exist.md"})
        assert removed2 == 0
        assert retriever.index.ntotal == 3


class TestHybridRetriever:
    def test_fused_results(self, sample_docs):
        vec = VectorRetriever(embedding_dim=768)
        vec.build_index(sample_docs)
        bm25 = BM25Retriever()
        bm25.build_index(sample_docs)

        hybrid = HybridRetriever(vec, bm25)
        results = hybrid.search("编程语言", SearchConfig(top_k=5, rerank_top_k=3))
        assert len(results) <= 3
        assert all(isinstance(doc, Document) for doc, score in results)


class TestPipelineMultiFormatRebuild:
    def test_obsidian_documents_are_split_before_indexing(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        index_dir = tmp_path / "index"
        vault.mkdir()
        (vault / ".obsidian").mkdir()
        (vault / "note.md").write_text(
            "# 测试笔记\n\n这是用于验证桌面端索引重建的正文内容。" * 4,
            encoding="utf-8",
        )

        monkeypatch.setenv("SPLIT_STRATEGY", "legacy")
        pipeline = SecondBrainPipeline(
            PipelineConfig(vault_path=str(vault), index_dir=str(index_dir))
        )
        vector = MagicMock()
        bm25 = MagicMock()

        def create_index_dir(path):
            Path(path).mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(pipeline, "save_index", create_index_dir)

        with (
            patch("src.retrievers.pipeline.VectorRetriever", return_value=vector),
            patch("src.retrievers.pipeline.BM25Retriever", return_value=bm25),
            patch("src.retrievers.pipeline.HybridRetriever"),
            patch("src.retrievers.pipeline.RAGRetriever"),
        ):
            stats = pipeline.rebuild_index_from_vault()

        indexed_docs = vector.build_index.call_args.args[0]
        assert stats["total_notes"] == 1
        assert indexed_docs
        assert all(isinstance(doc, Document) for doc in indexed_docs)
        assert indexed_docs[0].metadata["relative_path"] == "note.md"

    def test_multiformat_incremental_replaces_changed_file_chunks(self, tmp_path, monkeypatch):
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "faiss.index").write_bytes(b"placeholder")
        (index_dir / "documents.pkl").write_bytes(b"placeholder")

        pipeline = SecondBrainPipeline(
            PipelineConfig(vault_path=str(tmp_path / "vault"), index_dir=str(index_dir))
        )

        old_doc = Document(
            page_content="old content",
            metadata={"relative_path": "report.pdf", "domain": "通识", "content_hash": "old"},
        )
        vector = MagicMock()
        vector.documents = [old_doc]
        vector.remove_documents_by_relative_paths.return_value = 1

        def append_docs(docs):
            vector.documents = docs

        vector.add_documents.side_effect = append_docs
        bm25 = MagicMock()
        bm25.remove_documents_by_relative_paths.return_value = 1

        pipeline.vector_retriever = vector
        pipeline.bm25_retriever = bm25
        monkeypatch.setattr(pipeline, "save_index", lambda path: None)

        changed = [
            ParsedDocument(
                title="report",
                content="new content for report",
                source_file=str(tmp_path / "vault" / "report.pdf"),
                relative_path="report.pdf",
                folder="root",
                content_hash="new",
            )
        ]

        class FakeRouter:
            def __init__(self, *args, **kwargs):
                pass

            def parse_directory_incremental(self, manifest, include_types=None, exclude_dirs=None):
                return changed, ["removed.docx"]

        new_chunk = Document(
            page_content="new content for report",
            metadata={"relative_path": "report.pdf", "domain": "通识", "content_hash": "new"},
        )

        monkeypatch.setattr(
            "src.retrievers.pipeline.split_notes_to_documents",
            lambda docs, chunk_size, chunk_overlap: [new_chunk],
        )

        with (
            patch("src.parsers.document_router.DocumentRouter", FakeRouter),
            patch("src.retrievers.pipeline.HybridRetriever"),
            patch("src.retrievers.pipeline.RAGRetriever"),
        ):
            stats = pipeline.rebuild_index_from_vault(incremental=True)

        vector.remove_documents_by_relative_paths.assert_called_once_with(
            {"report.pdf", "removed.docx"}
        )
        bm25.remove_documents_by_relative_paths.assert_called_once_with(
            {"report.pdf", "removed.docx"}
        )
        vector.add_documents.assert_called_once_with([new_chunk])
        vector.build_index.assert_not_called()
        assert stats["total_notes"] == 1
        assert stats["total_chunks"] == 1

    def test_incremental_manifest_not_updated_when_save_fails(self, tmp_path, monkeypatch):
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "faiss.index").write_bytes(b"placeholder")
        (index_dir / "documents.pkl").write_bytes(b"placeholder")

        pipeline = SecondBrainPipeline(
            PipelineConfig(vault_path=str(tmp_path / "vault"), index_dir=str(index_dir))
        )

        old_doc = Document(
            page_content="old content",
            metadata={"relative_path": "report.pdf", "domain": "通识", "content_hash": "old"},
        )
        vector = MagicMock()
        vector.documents = [old_doc]

        pipeline.vector_retriever = vector
        pipeline.bm25_retriever = MagicMock()

        def raise_on_save(path):
            raise RuntimeError("disk full")

        monkeypatch.setattr(pipeline, "save_index", raise_on_save)

        changed = [
            ParsedDocument(
                title="report",
                content="new content for report",
                source_file=str(tmp_path / "vault" / "report.pdf"),
                relative_path="report.pdf",
                folder="root",
                content_hash="new",
            )
        ]

        monkeypatch.setattr(
            "src.retrievers.pipeline.split_notes_to_documents",
            lambda docs, chunk_size, chunk_overlap: [],
        )

        with pytest.raises(RuntimeError, match="disk full"):
            pipeline._apply_incremental_documents(changed, [], chunk_size=512)

        # save_index 失败后 manifest 不应被更新
        assert not (index_dir / "manifest.json").exists()
