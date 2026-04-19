"""RAG Pipeline — 端到端的检索增强生成流水线

整合：Obsidian解析 → 文档切分 → Embedding → 混合检索 → Rerank → LLM生成
"""

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


@dataclass
class PipelineConfig:
    """Pipeline 全局配置"""
    vault_path: str = ""
    index_dir: str = "data/index"
    chunk_size: int = 512
    chunk_overlap: int = 100
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


class SecondBrainPipeline:
    """SecondBrain Chat 核心流水线"""

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.vector_retriever = None
        self.bm25_retriever = None
        self.hybrid_retriever = None
        self.rag_retriever = None
        self.llm_generator = None
        self._stats = {}

    def build_index(self, vault_path: str = None, chunk_size: int = None):
        """从 Obsidian vault 构建全量索引"""
        vault_path = vault_path or self.config.vault_path
        chunk_size = chunk_size or self.config.chunk_size

        print(f"📂 解析 Obsidian vault: {vault_path}")
        parser = ObsidianParser(vault_path)
        notes = parser.parse_vault()
        print(f"📄 解析到 {len(notes)} 篇笔记")

        # 切分
        print(f"✂️  切分文档（chunk_size={chunk_size}）...")
        docs = split_notes_to_documents(notes, chunk_size=chunk_size, chunk_overlap=self.config.chunk_overlap)
        print(f"📝 切分为 {len(docs)} 个 chunks")

        # 统计
        from collections import Counter
        domains = Counter(doc.metadata["domain"] for doc in docs)
        self._stats = {
            "total_notes": len(notes),
            "total_chunks": len(docs),
            "domain_distribution": dict(domains.most_common()),
        }
        print(f"📊 领域分布: {dict(domains.most_common())}")

        # 构建向量索引
        self.vector_retriever = VectorRetriever()
        self.vector_retriever.build_index(docs)

        # 构建 BM25 索引
        self.bm25_retriever = BM25Retriever()
        self.bm25_retriever.build_index(docs)

        # 组装混合检索器
        self.hybrid_retriever = HybridRetriever(self.vector_retriever, self.bm25_retriever)
        self.rag_retriever = RAGRetriever(self.hybrid_retriever)

        # 保存索引
        self.save_index(self.config.index_dir)
        print(f"✅ 索引构建完成，已保存到 {self.config.index_dir}")

        return self._stats

    def load_index(self, index_dir: str = None):
        """加载已构建的索引"""
        index_dir = index_dir or self.config.index_dir
        print(f"📂 加载索引: {index_dir}")

        # 加载向量索引
        self.vector_retriever = VectorRetriever()
        self.vector_retriever.load(index_dir)

        # BM25 索引
        bm25_path = os.path.join(index_dir, "bm25.pkl")
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
        stats_path = os.path.join(index_dir, "stats.json")
        if os.path.exists(stats_path):
            with open(stats_path, "r") as f:
                self._stats = json.load(f)

        print(f"✅ 索引加载完成（{self.vector_retriever.index.ntotal} 个向量）")

    def chat(self, query: str, domain: str = None, top_k: int = None) -> dict:
        """同步对话（非流式）"""
        if self.rag_retriever is None:
            raise RuntimeError("请先调用 build_index() 或 load_index()")

        if self.llm_generator is None:
            llm_config = LLMConfig(
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
            )
            self.llm_generator = LLMGenerator(llm_config)

        # 检索
        config = SearchConfig(
            top_k=top_k or self.config.default_top_k,
            rerank_top_k=self.config.default_rerank_top_k,
            bm25_weight=self.config.bm25_weight,
            vector_weight=self.config.vector_weight,
            domain_filter=domain,
        )
        results = self.rag_retriever.retrieve(query, config)

        if not results:
            return {
                "answer": "抱歉，知识库中没有找到与您问题相关的内容。",
                "sources": [],
                "query": query,
            }

        # 生成答案
        docs = [doc for doc, _ in results]
        answer = self.llm_generator.generate(query, docs)

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

    async def chat_stream(self, query: str, domain: str = None, top_k: int = None) -> AsyncGenerator[str, None]:
        """流式对话"""
        if self.rag_retriever is None:
            raise RuntimeError("请先调用 build_index() 或 load_index()")

        if self.llm_generator is None:
            llm_config = LLMConfig(
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
            )
            self.llm_generator = LLMGenerator(llm_config)

        # 检索
        config = SearchConfig(
            top_k=top_k or self.config.default_top_k,
            rerank_top_k=self.config.default_rerank_top_k,
            bm25_weight=self.config.bm25_weight,
            vector_weight=self.config.vector_weight,
            domain_filter=domain,
        )
        results = self.rag_retriever.retrieve(query, config)

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
        async for chunk in self.llm_generator.generate_stream(query, docs):
            yield chunk

    def save_index(self, index_dir: str):
        """保存所有索引"""
        os.makedirs(index_dir, exist_ok=True)
        self.vector_retriever.save(index_dir)

        # 保存 BM25
        with open(os.path.join(index_dir, "bm25.pkl"), "wb") as f:
            pickle.dump(self.bm25_retriever, f)

        # 保存统计
        with open(os.path.join(index_dir, "stats.json"), "w") as f:
            json.dump(self._stats, f, ensure_ascii=False, indent=2)

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
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
