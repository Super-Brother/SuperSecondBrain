"""测试检索器"""

import sys
from pathlib import Path

import numpy as np
import pytest
from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrievers.rag_retriever import (
    VectorRetriever,
    BM25Retriever,
    HybridRetriever,
    SearchConfig,
)


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
