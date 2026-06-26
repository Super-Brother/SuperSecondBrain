"""RAG Pipeline — 端到端的检索增强生成流水线

整合：Obsidian解析 → 文档切分 → Embedding → 混合检索 → Rerank → LLM生成
"""

import hashlib
import os
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator

from langchain_core.documents import Document

from src.parsers.obsidian_parser import ObsidianParser
from src.parsers.text_splitter import split_notes_to_documents
from src.retrievers.rag_retriever import (
    VectorRetriever,
    BM25Retriever,
    HybridRetriever,
    RAGRetriever,
    SearchConfig,
)
from src.models.llm_generator import LLMGenerator, LLMConfig
from src.retrievers.query_rewriter import QueryRewriter
from src.utils.index_version import IndexVersionManager


@dataclass
class PipelineConfig:
    """Pipeline 全局配置"""
    vault_path: str = ""
    index_dir: str = "data/index"
    chunk_size: int = 512
    chunk_overlap: int = 100
    # 模型路径：优先本地 models/ 目录，不存在时自动从 HuggingFace 下载
    # 可通过环境变量 EMBEDDING_MODEL / RERANKER_MODEL 覆盖
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    # LLM 配置
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.3
    # 检索配置
    default_top_k: int = 10
    default_rerank_top_k: int = 5
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    enable_query_rewrite: bool = False
    # 索引版本管理
    versioned: bool = False  # 是否启用版本化索引（自动多版本+灰度切换）


class SecondBrainPipeline:
    """SecondBrain Chat 核心流水线"""

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.vector_retriever = None
        self.bm25_retriever = None
        self.hybrid_retriever = None
        self.rag_retriever = None
        self.llm_generator = None
        self.query_rewriter = None
        self._stats = {}
        # 索引版本管理器（可选启用，默认兼容旧版无版本化模式）
        self.version_manager = IndexVersionManager(self.config.index_dir)

    def build_index(self, vault_path: str = None, chunk_size: int = None, incremental: bool = False):
        """从 Obsidian vault 构建索引，支持增量模式"""
        vault_path = vault_path or self.config.vault_path
        chunk_size = chunk_size or self.config.chunk_size

        parser = ObsidianParser(vault_path)

        if incremental:
            return self._build_index_incremental(parser, chunk_size)
        return self._build_index_full(parser, chunk_size)

    @staticmethod
    def _write_json_atomic(path: str, data: dict) -> None:
        """原子写入 JSON 文件：先写临时文件，再 os.replace 到目标路径。

        避免 manifest/stats 写入中断导致旧文件不可用。
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)

    def _build_index_full(self, parser, chunk_size: int):
        """全量构建索引"""
        notes = parser.parse_vault()
        print(f"📄 解析到 {len(notes)} 篇笔记")

        print(f"✂️  切分文档（chunk_size={chunk_size}）...")
        docs = split_notes_to_documents(notes, chunk_size=chunk_size, chunk_overlap=self.config.chunk_overlap)
        print(f"📝 切分为 {len(docs)} 个 chunks")

        from collections import Counter
        domains = Counter(doc.metadata["domain"] for doc in docs)
        self._stats = {
            "total_notes": len(notes),
            "total_chunks": len(docs),
            "domain_distribution": dict(domains.most_common()),
        }
        print(f"📊 领域分布: {dict(domains.most_common())}")

        self.vector_retriever = VectorRetriever()
        self.vector_retriever.build_index(docs)

        self.bm25_retriever = BM25Retriever()
        self.bm25_retriever.build_index(docs)

        self.hybrid_retriever = HybridRetriever(self.vector_retriever, self.bm25_retriever)
        self.rag_retriever = RAGRetriever(self.hybrid_retriever)

        # 生成 manifest
        manifest = {}
        for doc in docs:
            rp = doc.metadata.get("relative_path", "")
            h = doc.metadata.get("content_hash", "")
            if rp and h:
                manifest[rp] = h

        if self.config.versioned:
            version_id = self.save_index_versioned()
            manifest_path = os.path.join(str(self.version_manager.get_version_path(version_id)), "manifest.json")
            print(f"✅ 索引构建完成，新版本: {version_id}")
        else:
            self.save_index(self.config.index_dir)
            manifest_path = os.path.join(self.config.index_dir, "manifest.json")
            print(f"✅ 索引构建完成，已保存到 {self.config.index_dir}")

        self._write_json_atomic(manifest_path, manifest)

        return self._stats

    def _build_index_incremental(self, parser, chunk_size: int):
        """增量构建索引：只处理新增/变更的文件

        优化后：若已有索引加载在内存中，只对新 chunks 计算 Embedding 并追加，
        删除时仅重建必要的部分；否则回退到全量重建（首次构建/索引损坏）。
        """
        manifest_path = os.path.join(self.config.index_dir, "manifest.json")
        manifest = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

        print(f"📂 增量解析（已有 {len(manifest)} 个文件记录）...")
        changed_notes, deleted = parser.parse_vault_incremental(manifest)
        print(f"📄 新增/变更: {len(changed_notes)} 篇，删除: {len(deleted)} 篇")

        if not changed_notes and not deleted:
            print("✅ 无变更，跳过索引重建")
            return self._stats

        return self._apply_incremental_documents(changed_notes, deleted, chunk_size, label="增量")

    def _apply_incremental_documents(
        self,
        changed_notes,
        deleted: list[str],
        chunk_size: int,
        label: str = "增量",
    ):
        """Apply changed/deleted parsed documents without re-embedding unchanged chunks."""
        changed_paths = {
            note.relative_path
            for note in changed_notes
            if getattr(note, "relative_path", "")
        }
        affected_paths = set(deleted) | changed_paths

        print("✂️ 切分变更文档...")
        new_docs = split_notes_to_documents(
            changed_notes, chunk_size=chunk_size, chunk_overlap=self.config.chunk_overlap
        )
        print(f"📝 新增 {len(new_docs)} 个 chunks")

        can_incremental = (
            self.vector_retriever is not None
            and self.bm25_retriever is not None
            and os.path.exists(os.path.join(self.config.index_dir, "faiss.index"))
            and os.path.exists(os.path.join(self.config.index_dir, "documents.pkl"))
        )

        if can_incremental:
            if affected_paths:
                print(f"🗑️ 删除 {len(affected_paths)} 个旧文件对应的 chunks...")
                vector_removed = self.vector_retriever.remove_documents_by_relative_paths(affected_paths)
                bm25_removed = self.bm25_retriever.remove_documents_by_relative_paths(affected_paths)
                print(f"🗑️ 向量索引删除 {vector_removed} 个 chunks，BM25 删除 {bm25_removed} 个")

            if new_docs:
                print(f"➕ 追加 {len(new_docs)} 个新 chunks 到现有索引...")
                self.vector_retriever.add_documents(new_docs)
                self.bm25_retriever.add_documents(new_docs)

            all_docs = self.vector_retriever.documents
        else:
            print("⚠️ 未检测到已加载索引，回退到全量重建...")
            old_docs = []
            docs_path = os.path.join(self.config.index_dir, "documents.pkl")
            if os.path.exists(docs_path):
                with open(docs_path, "rb") as f:
                    old_docs = pickle.load(f)

            filtered_old = [
                d for d in old_docs if d.metadata.get("relative_path", "") not in affected_paths
            ]
            all_docs = filtered_old + new_docs

            self.vector_retriever = VectorRetriever()
            self.vector_retriever.build_index(all_docs)

            self.bm25_retriever = BM25Retriever()
            self.bm25_retriever.build_index(all_docs)

        from collections import Counter

        domains = Counter(doc.metadata["domain"] for doc in all_docs)
        self._stats = {
            "total_notes": len(set(doc.metadata.get("relative_path", "") for doc in all_docs)),
            "total_chunks": len(all_docs),
            "domain_distribution": dict(domains.most_common()),
        }

        self.hybrid_retriever = HybridRetriever(self.vector_retriever, self.bm25_retriever)
        self.rag_retriever = RAGRetriever(self.hybrid_retriever)

        new_manifest = {}
        for doc in all_docs:
            rp = doc.metadata.get("relative_path", "")
            h = doc.metadata.get("content_hash", "")
            if rp and h:
                new_manifest[rp] = h

        if self.config.versioned:
            version_id = self.save_index_versioned()
            manifest_path = os.path.join(str(self.version_manager.get_version_path(version_id)), "manifest.json")
            print(f"✅ {label}索引完成，新版本: {version_id}（共 {len(all_docs)} chunks）")
        else:
            self.save_index(self.config.index_dir)
            manifest_path = os.path.join(self.config.index_dir, "manifest.json")
            print(f"✅ {label}索引完成（共 {len(all_docs)} chunks）")

        self._write_json_atomic(manifest_path, new_manifest)

        return self._stats

    def load_index(self, index_dir: str = None):
        """加载已构建的索引（自动识别版本化管理）"""
        if index_dir:
            target_dir = index_dir
        else:
            # 优先使用版本管理器解析当前应加载的目录
            target_dir = self.version_manager.get_current_index_dir()
            current_version = self.version_manager.get_current_version()
            if current_version and current_version != "__legacy__":
                print(f"📂 加载索引版本: {current_version}")
        print(f"📂 加载索引目录: {target_dir}")

        # 加载向量索引
        self.vector_retriever = VectorRetriever()
        self.vector_retriever.load(target_dir)

        # BM25 索引
        bm25_path = os.path.join(target_dir, "bm25.pkl")
        if os.path.exists(bm25_path):
            with open(bm25_path, "rb") as f:
                self.bm25_retriever = pickle.load(f)
        else:
            # 从向量索引的 documents 重建
            print("[WARN] BM25 索引不存在，从向量索引重建...")
            self.bm25_retriever = BM25Retriever()
            self.bm25_retriever.build_index(self.vector_retriever.documents)

        self.hybrid_retriever = HybridRetriever(self.vector_retriever, self.bm25_retriever)
        self.rag_retriever = RAGRetriever(self.hybrid_retriever)

        # 初始化 LLM
        llm_config = LLMConfig(
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            model=self.config.llm_model,
            temperature=self.config.llm_temperature,
        )
        self.llm_generator = LLMGenerator(llm_config)

        # 加载统计
        stats_path = os.path.join(target_dir, "stats.json")
        if os.path.exists(stats_path):
            with open(stats_path, "r") as f:
                self._stats = json.load(f)

        print(f"✅ 索引加载完成（{self.vector_retriever.index.ntotal} 个向量）")

    def warmup(self):
        """预热：预加载所有延迟初始化的组件（Reranker、LLM、Embedder）"""
        print("[Warmup] 开始预热...")

        # 1. 预热 Reranker（最耗时，模型几百MB）
        if self.rag_retriever is not None:
            try:
                _ = self.rag_retriever.reranker
                print("[Warmup] Reranker 加载完成")
            except Exception as e:
                print(f"[Warmup] Reranker 加载失败: {e}")

        # 2. 预热 Embedding（触发 embedder 加载）
        if self.vector_retriever is not None:
            try:
                _ = self.vector_retriever.embedder
                print("[Warmup] Embedding 加载完成")
            except Exception as e:
                print(f"[Warmup] Embedding 加载失败: {e}")

        # 3. 预热 LLM（初始化客户端）
        self._ensure_llm()
        print("[Warmup] LLM 客户端初始化完成")

        print("[Warmup] 预热完成")

    def _ensure_llm(self):
        """延迟初始化 LLM 和 QueryRewriter"""
        if self.llm_generator is None:
            llm_config = LLMConfig(
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
            )
            self.llm_generator = LLMGenerator(llm_config)

        if self.query_rewriter is None and self.config.enable_query_rewrite:
            self.query_rewriter = QueryRewriter(
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                model=self.config.llm_model,
            )

    def switch_llm(self, llm_config: LLMConfig) -> dict:
        """运行时切换 LLM 配置"""
        self.config.llm_base_url = llm_config.base_url
        self.config.llm_api_key = llm_config.api_key
        self.config.llm_model = llm_config.model
        self.config.llm_temperature = llm_config.temperature

        if self.llm_generator:
            self.llm_generator.update_config(llm_config)
        else:
            self.llm_generator = LLMGenerator(llm_config)

        # 重置 QueryRewriter
        self.query_rewriter = None

        return {
            "status": "ok",
            "model": llm_config.model,
            "base_url": llm_config.base_url,
        }

    def _rewrite_query(self, query: str) -> tuple[str, str]:
        """查询改写，返回 (改写后查询, 原始查询)"""
        if self.query_rewriter:
            try:
                rewritten = self.query_rewriter.rewrite(query)
                print(f"[QueryRewrite] '{query}' → '{rewritten}'")
                return rewritten, query
            except Exception:
                pass
        return query, query

    def chat(self, query: str, domain: str = None, top_k: int = None, history: list[dict] | None = None) -> dict:
        """同步对话（非流式），支持多轮历史"""
        if self.rag_retriever is None:
            raise RuntimeError("请先调用 build_index() 或 load_index()")

        self._ensure_llm()
        search_query, _ = self._rewrite_query(query)

        # 检索
        config = SearchConfig(
            top_k=top_k or self.config.default_top_k,
            rerank_top_k=self.config.default_rerank_top_k,
            bm25_weight=self.config.bm25_weight,
            vector_weight=self.config.vector_weight,
            domain_filter=domain,
        )
        results = self.rag_retriever.retrieve(search_query, config)

        if not results:
            return {
                "answer": "抱歉，知识库中没有找到与您问题相关的内容。",
                "sources": [],
                "query": query,
            }

        # 生成答案
        docs = [doc for doc, _ in results]
        answer = self.llm_generator.generate(query, docs, history=history)

        # 构建来源信息
        sources = [
            {
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source_file", ""),
                "folder": doc.metadata.get("folder", ""),
                "domain": doc.metadata.get("domain", ""),
                "tags": doc.metadata.get("tags", []),
                "score": round(score, 3),
            }
            for doc, score in results
        ]

        return {
            "answer": answer,
            "sources": sources,
            "query": query,
        }

    async def chat_stream(self, query: str, domain: str = None, top_k: int = None, history: list[dict] | None = None) -> AsyncGenerator[str, None]:
        """流式对话，支持多轮历史"""
        if self.rag_retriever is None:
            raise RuntimeError("请先调用 build_index() 或 load_index()")

        self._ensure_llm()
        search_query, _ = self._rewrite_query(query)

        # 检索
        config = SearchConfig(
            top_k=top_k or self.config.default_top_k,
            rerank_top_k=self.config.default_rerank_top_k,
            bm25_weight=self.config.bm25_weight,
            vector_weight=self.config.vector_weight,
            domain_filter=domain,
        )
        results = self.rag_retriever.retrieve(search_query, config)

        if not results:
            yield "抱歉，知识库中没有找到与您问题相关的内容。"
            return

        docs = [doc for doc, _ in results]

        # 先返回来源信息（JSON 格式）
        sources = [
            {
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source_file", ""),
                "domain": doc.metadata.get("domain", ""),
                "score": round(score, 3),
            }
            for doc, score in results
        ]
        yield f"__SOURCES__:{json.dumps(sources, ensure_ascii=False)}\n"

        # 流式生成答案
        async for chunk in self.llm_generator.generate_stream(query, docs, history=history):
            yield chunk

    def save_index(self, index_dir: str):
        """保存所有索引（向后兼容：直接保存到指定目录）"""
        os.makedirs(index_dir, exist_ok=True)
        self._save_index_to_dir(index_dir)

    def save_index_versioned(self) -> str:
        """版本化保存索引：创建新版本目录，保存后自动切换并清理旧版本

        Returns:
            新版本 ID
        """
        version_id = self.version_manager.create_version_dir()
        version_dir = self.version_manager.get_version_path(version_id)
        print(f"💾 保存索引到新版本: {version_id}")

        self._save_index_to_dir(str(version_dir))

        # 原子切换到新版本
        result = self.version_manager.switch_version(version_id)
        print(f"✅ 已切换至版本 {version_id}（上一版本: {result.get('previous') or '无'}）")

        # 清理超出的旧版本
        deleted = self.version_manager.cleanup_old_versions()
        if deleted:
            print(f"🧹 已清理旧版本: {', '.join(deleted)}")

        return version_id

    def _save_index_to_dir(self, index_dir: str):
        """实际保存索引文件到指定目录"""
        os.makedirs(index_dir, exist_ok=True)
        self.vector_retriever.save(index_dir)

        # 保存 BM25
        with open(os.path.join(index_dir, "bm25.pkl"), "wb") as f:
            pickle.dump(self.bm25_retriever, f)

        # 保存统计
        stats_path = os.path.join(index_dir, "stats.json")
        self._write_json_atomic(stats_path, self._stats)

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        return self._stats

    def rebuild_index_from_vault(
        self, vault_path: str = None, chunk_size: int = None, incremental: bool = False
    ):
        """从 vault 目录重建索引，支持多格式（.md / .pdf / .docx / .pptx / .xlsx）

        与 build_index() 的区别：
        - build_index() 使用 ObsidianParser，只处理 .md
        - rebuild_index_from_vault() 使用 DocumentRouter，处理所有注册格式
        """
        vault_path = vault_path or self.config.vault_path
        chunk_size = chunk_size or self.config.chunk_size

        from src.parsers.document_router import DocumentRouter

        print(f"📂 多格式解析 vault: {vault_path}")
        router = DocumentRouter(vault_path, use_obsidian=True)

        if incremental:
            manifest_path = os.path.join(self.config.index_dir, "manifest.json")
            manifest = {}
            if os.path.exists(manifest_path):
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)

            print(f"📂 多格式增量解析（已有 {len(manifest)} 个文件记录）...")
            changed_docs, deleted = router.parse_directory_incremental(manifest)
            print(f"📄 新增/变更: {len(changed_docs)} 个文档，删除: {len(deleted)} 个文档")
            if not changed_docs and not deleted:
                print("✅ 无变更，跳过索引重建")
                return self._stats
            return self._apply_incremental_documents(
                changed_docs, deleted, chunk_size, label="多格式增量"
            )

        parsed_docs = router.parse_directory(vault_path)
        print(f"📄 解析到 {len(parsed_docs)} 个文档")

        print(f"✂️  切分文档（chunk_size={chunk_size}）...")
        all_docs = split_notes_to_documents(
            parsed_docs,
            chunk_size=chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        print(f"📝 切分为 {len(all_docs)} 个 chunks")

        # 补齐元数据（与 Obsidian 解析路径对齐）
        from src.parsers.obsidian_parser import classify_domain
        vault_path_obj = Path(vault_path)
        for doc in all_docs:
            source = doc.metadata.get("source_file", "")
            try:
                rel_path = str(Path(source).relative_to(vault_path_obj))
            except ValueError:
                rel_path = source

            if "relative_path" not in doc.metadata:
                doc.metadata["relative_path"] = rel_path
            if "content_hash" not in doc.metadata:
                doc.metadata["content_hash"] = hashlib.md5(doc.page_content.encode()).hexdigest()
            if "domain" not in doc.metadata:
                folder = doc.metadata.get("folder", "")
                doc.metadata["domain"] = classify_domain(folder)

        # 统计
        from collections import Counter
        domains = Counter(doc.metadata.get("domain", "其他") for doc in all_docs)
        sources = set(doc.metadata.get("relative_path", "") for doc in all_docs)
        self._stats = {
            "total_notes": len(sources),
            "total_chunks": len(all_docs),
            "domain_distribution": dict(domains.most_common()),
        }
        print(f"📊 领域分布: {dict(domains.most_common())}")

        # 重建索引
        self.vector_retriever = VectorRetriever()
        if all_docs:
            self.vector_retriever.build_index(all_docs)

        self.bm25_retriever = BM25Retriever()
        if all_docs:
            self.bm25_retriever.build_index(all_docs)

        self.hybrid_retriever = HybridRetriever(self.vector_retriever, self.bm25_retriever)
        self.rag_retriever = RAGRetriever(self.hybrid_retriever)

        # 生成 manifest（全量）
        manifest = {}
        for doc in all_docs:
            rp = doc.metadata.get("relative_path", "")
            h = doc.metadata.get("content_hash", "")
            if rp and h:
                manifest[rp] = h

        if self.config.versioned:
            version_id = self.save_index_versioned()
            manifest_path = os.path.join(str(self.version_manager.get_version_path(version_id)), "manifest.json")
            print(f"✅ 多格式索引重建完成，新版本: {version_id}")
        else:
            self.save_index(self.config.index_dir)
            manifest_path = os.path.join(self.config.index_dir, "manifest.json")
            print(f"✅ 多格式索引重建完成，已保存到 {self.config.index_dir}")

        self._write_json_atomic(manifest_path, manifest)
        return self._stats


if __name__ == "__main__":
    # 测试完整流水线
    config = PipelineConfig(
        vault_path="/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本",
    )
    pipeline = SecondBrainPipeline(config)

    # 构建索引（首次运行）
    stats = pipeline.build_index()
    print(f"\n统计: {json.dumps(stats, ensure_ascii=False, indent=2)}")

    # 加载索引（后续运行）
    # pipeline.load_index()

    # 测试对话
    # result = pipeline.chat("怎么保持组织的创新能力")
    # print(f"\nQ: {result['query']}")
    # print(f"A: {result['answer']}")
    # print(f"来源: {[s['title'][:30] for s in result['sources']]}")
