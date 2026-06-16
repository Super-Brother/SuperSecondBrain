"""RAG 检索器

核心检索能力：
- 向量检索（FAISS + BGE Embedding）
- BM25 关键词检索（jieba 分词）
- 混合检索（分数融合）
- Rerank 重排序
- 领域过滤
"""

import os
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# macOS 上必须先初始化 torch，再导入 faiss/jieba，
# 避免 PyTorch 线程状态与 faiss/jieba 多线程冲突导致的段错误
import torch  # noqa: F401

import faiss
import jieba
from rank_bm25 import BM25Okapi

from langchain_core.documents import Document


@dataclass
class SearchConfig:
    """检索配置"""
    top_k: int = 10           # 初检数量
    rerank_top_k: int = 5     # 重排后返回数量
    bm25_weight: float = 0.3  # BM25 分数权重
    vector_weight: float = 0.7 # 向量分数权重
    domain_filter: str | None = None  # 领域过滤
    # 权限过滤（企业级）
    user_departments: list[str] | None = None  # 用户所属部门
    user_access_level: int | None = None      # 用户访问级别


class VectorRetriever:
    """向量检索器 — 支持 FAISS（本地）和 Milvus（分布式）后端"""

    def __init__(self, embedding_dim: int = None, backend: str = None):
        self.embedding_dim = embedding_dim
        self.backend = backend or os.getenv("VECTOR_STORE_BACKEND", "faiss")
        self._store = None
        self._embedder = None

    @property
    def store(self):
        if self._store is None:
            from src.retrievers.vector_store import FAISSVectorStore, MilvusVectorStore, VectorStoreConfig

            config = VectorStoreConfig(embedding_dim=self.embedding_dim or 768)
            if self.backend == "milvus":
                config.host = os.getenv("MILVUS_HOST", "localhost")
                config.port = int(os.getenv("MILVUS_PORT", "19530"))
                config.collection_name = os.getenv("MILVUS_COLLECTION", "enterprise_kb")
                config.index_type = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
                config.metric_type = os.getenv("MILVUS_METRIC_TYPE", "COSINE")
                config.enable_acl = os.getenv("MILVUS_ENABLE_ACL", "false").lower() == "true"
                self._store = MilvusVectorStore(config)
            else:
                self._store = FAISSVectorStore(config)
        return self._store

    @property
    def embedder(self):
        return self.store.embedder

    @property
    def documents(self) -> list[Document]:
        return self.store.documents

    @property
    def index(self):
        """兼容旧代码，仅在 FAISS 后端有效"""
        if hasattr(self.store, "index"):
            return self.store.index
        return None

    def build_index(self, documents: list[Document]):
        """构建向量索引"""
        print(f"[VectorRetriever] 正在对 {len(documents)} 个 chunks 做 Embedding...")
        texts = [doc.page_content for doc in documents]
        batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
        embeddings = self.embedder.encode(texts, show_progress_bar=True, batch_size=batch_size)

        if self.embedding_dim is None:
            self.embedding_dim = embeddings.shape[1]
            print(f"[VectorRetriever] Embedding 维度: {self.embedding_dim}")

        self.store.add_documents(documents, embeddings=embeddings.tolist())
        stats = self.store.get_stats()
        print(f"[VectorRetriever] 索引构建完成，共 {stats.get('total_vectors', 0)} 个向量")

    def add_documents(self, documents: list[Document]):
        """仅对新文档计算 Embedding 并追加到现有索引"""
        if not documents:
            return

        print(f"[VectorRetriever] 正在对 {len(documents)} 个新增 chunks 做 Embedding...")
        texts = [doc.page_content for doc in documents]
        batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
        embeddings = self.embedder.encode(texts, show_progress_bar=True, batch_size=batch_size)

        if self.embedding_dim is None:
            self.embedding_dim = embeddings.shape[1]

        self.store.add_documents(documents, embeddings=embeddings.tolist())
        stats = self.store.get_stats()
        print(f"[VectorRetriever] 追加完成，共 {stats.get('total_vectors', 0)} 个向量")

    def remove_documents_by_relative_paths(self, relative_paths: set[str]) -> int:
        """删除指定 relative_path 的文档"""
        return self.store.remove_documents_by_relative_paths(relative_paths)

    def search(
        self,
        query: str,
        top_k: int = 10,
        domain: str | None = None,
        user_departments: list[str] | None = None,
        user_access_level: int | None = None,
    ) -> list[tuple[Document, float]]:
        """向量检索，支持领域过滤和权限过滤"""
        filter_expr = None
        if domain:
            filter_expr = {"domain": domain}

        # Milvus 权限过滤：通过元数据过滤表达式
        if self.backend == "milvus" and user_departments is not None and user_access_level is not None:
            dept_list = ", ".join(f'"{d}"' for d in user_departments)
            acl_expr = f'department in [{dept_list}] and access_level <= {user_access_level}'
            if filter_expr:
                # 合并过滤条件
                filter_expr = f"{filter_expr} and {acl_expr}"
            else:
                filter_expr = acl_expr

        results = self.store.search(query_text=query, top_k=top_k, filter_expr=filter_expr)

        # FAISS 权限过滤：内存过滤（ Milvus 已在服务端过滤）
        if self.backend != "milvus" and user_departments is not None and user_access_level is not None:
            filtered = []
            for r in results:
                doc = r.document
                doc_depts = doc.metadata.get("department", ["default"])
                if isinstance(doc_depts, str):
                    doc_depts = [doc_depts]
                doc_level = doc.metadata.get("access_level", 0)
                if any(d in doc_depts for d in user_departments) and doc_level <= user_access_level:
                    filtered.append(r)
            results = filtered

        return [(r.document, r.score) for r in results]

    def save(self, path: str):
        """保存索引"""
        self.store.save(path)

    def load(self, path: str):
        """加载索引"""
        self.store.load(path)
        stats = self.store.get_stats()
        print(f"[VectorRetriever] 加载索引完成，共 {stats.get('total_vectors', 0)} 个向量")


class BM25Retriever:
    """BM25 关键词检索器"""

    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.documents: list[Document] = []
        self.tokenized_corpus: list[list[str]] = []

    def build_index(self, documents: list[Document]):
        """构建 BM25 索引"""
        self.documents = documents
        self.tokenized_corpus = [
            list(jieba.cut(doc.page_content)) for doc in documents
        ]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        print(f"[BM25Retriever] 索引构建完成，共 {len(documents)} 个文档")

    def add_documents(self, documents: list[Document]):
        """追加 BM25 文档；已有 index 时增量扩展 corpus"""
        if not documents:
            return

        if self.bm25 is None:
            self.build_index(documents)
            return

        self.documents.extend(documents)
        new_tokens = [list(jieba.cut(doc.page_content)) for doc in documents]
        self.tokenized_corpus.extend(new_tokens)
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        print(f"[BM25Retriever] 追加完成，共 {len(self.documents)} 个文档")

    def remove_documents_by_relative_paths(self, relative_paths: set[str]) -> int:
        """删除文档后重建 BM25 index"""
        if not relative_paths or not self.documents:
            return 0

        keep = [
            (doc, tokens)
            for doc, tokens in zip(self.documents, self.tokenized_corpus)
            if doc.metadata.get("relative_path", "") not in relative_paths
        ]
        removed_count = len(self.documents) - len(keep)
        if removed_count == 0:
            return 0

        self.documents = [doc for doc, _ in keep]
        self.tokenized_corpus = [tokens for _, tokens in keep]
        self.bm25 = BM25Okapi(self.tokenized_corpus) if self.tokenized_corpus else None
        print(f"[BM25Retriever] 删除 {removed_count} 个文档，剩余 {len(self.documents)} 个")
        return removed_count

    def search(
        self,
        query: str,
        top_k: int = 10,
        domain: str | None = None,
        user_departments: list[str] | None = None,
        user_access_level: int | None = None,
    ) -> list[tuple[Document, float]]:
        """BM25 检索，支持领域过滤和权限过滤"""
        tokenized_query = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokenized_query)

        # 归一化分数到 [0, 1]
        max_score = max(scores) if max(scores) > 0 else 1
        scores = scores / max_score

        # 排序
        doc_scores = list(enumerate(scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in doc_scores:
            doc = self.documents[idx]
            if domain and doc.metadata.get("domain") != domain:
                continue
            # 权限过滤
            if user_departments is not None and user_access_level is not None:
                doc_depts = doc.metadata.get("department", ["default"])
                if isinstance(doc_depts, str):
                    doc_depts = [doc_depts]
                doc_level = doc.metadata.get("access_level", 0)
                if not (any(d in doc_depts for d in user_departments) and doc_level <= user_access_level):
                    continue
            if score < 0.01:  # 忽略太低分
                break
            results.append((doc, float(score)))
            if len(results) >= top_k:
                break

        return results


class HybridRetriever:
    """混合检索器（BM25 + 向量，分数加权融合）"""

    def __init__(self, vector_retriever: VectorRetriever, bm25_retriever: BM25Retriever):
        self.vector = vector_retriever
        self.bm25 = bm25_retriever

    def search(self, query: str, config: SearchConfig = None) -> list[tuple[Document, float]]:
        """混合检索 + 分数融合"""
        if config is None:
            config = SearchConfig()

        # 分别检索（传递权限过滤参数）
        vector_results = self.vector.search(
            query,
            top_k=config.top_k,
            domain=config.domain_filter,
            user_departments=config.user_departments,
            user_access_level=config.user_access_level,
        )
        bm25_results = self.bm25.search(
            query,
            top_k=config.top_k,
            domain=config.domain_filter,
            user_departments=config.user_departments,
            user_access_level=config.user_access_level,
        )

        # 分数融合
        doc_scores = {}

        for doc, score in vector_results:
            doc_id = id(doc)
            doc_scores[doc_id] = doc_scores.get(doc_id, {"doc": doc, "vector": 0, "bm25": 0})
            doc_scores[doc_id]["vector"] = score
            doc_scores[doc_id]["doc"] = doc

        for doc, score in bm25_results:
            doc_id = id(doc)
            doc_scores[doc_id] = doc_scores.get(doc_id, {"doc": doc, "vector": 0, "bm25": 0})
            doc_scores[doc_id]["bm25"] = score
            doc_scores[doc_id]["doc"] = doc

        # 加权融合
        fused = []
        for doc_id, data in doc_scores.items():
            final_score = (
                data["vector"] * config.vector_weight +
                data["bm25"] * config.bm25_weight
            )
            fused.append((data["doc"], final_score))

        # 去重 + 排序
        seen = set()
        unique_results = []
        for doc, score in sorted(fused, key=lambda x: x[1], reverse=True):
            key = doc.metadata.get("source_file", "") + str(doc.metadata.get("chunk_index", ""))
            if key not in seen:
                seen.add(key)
                unique_results.append((doc, score))

        return unique_results[:config.rerank_top_k]


class RAGRetriever:
    """完整的 RAG 检索器（混合检索 + Rerank）"""

    def __init__(self, hybrid: HybridRetriever):
        self.hybrid = hybrid
        self._reranker = None

    @property
    def reranker(self):
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            import os
            from src.utils.model_resolver import resolve_model_path
            model_name = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
            model_path = resolve_model_path(model_name)
            cache_dir = os.getenv("SENTENCE_TRANSFORMERS_HOME")
            kwargs = {}
            if cache_dir:
                kwargs["model_kwargs"] = {"cache_dir": cache_dir}
            kwargs.setdefault("device", "cpu")
            self._reranker = CrossEncoder(model_path, **kwargs)
        return self._reranker

    def retrieve(self, query: str, config: SearchConfig = None) -> list[tuple[Document, float]]:
        """完整检索流程：混合检索 → Rerank"""
        if config is None:
            config = SearchConfig()

        # 第一步：混合检索
        candidates = self.hybrid.search(query, config)

        if not candidates:
            return []

        # 第二步：Rerank 重排序
        docs = [doc for doc, _ in candidates]
        query_doc_pairs = [(query, doc.page_content) for doc in docs]

        print(f"[Rerank] 对 {len(query_doc_pairs)} 个候选做重排序...")
        rerank_scores = self.reranker.predict(query_doc_pairs, show_progress_bar=False)

        # 按重排分数排序
        reranked = sorted(
            zip(docs, rerank_scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        return [(doc, float(score)) for doc, score in reranked[:config.rerank_top_k]]


if __name__ == "__main__":
    # 测试混合检索
    from src.parsers.obsidian_parser import ObsidianParser
    from src.parsers.text_splitter import split_notes_to_documents

    vault = "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    parser = ObsidianParser(vault)
    notes = parser.parse_vault()
    docs = split_notes_to_documents(notes)

    print(f"\n构建索引...")
    vector = VectorRetriever()
    vector.build_index(docs[:500])  # 先用前500个测试

    bm25 = BM25Retriever()
    bm25.build_index(docs[:500])

    hybrid = HybridRetriever(vector, bm25)
    rag = RAGRetriever(hybrid)

    # 测试检索
    query = "怎么保持组织的创新能力"
    results = rag.retrieve(query)
    print(f"\n查询: {query}")
    for doc, score in results:
        print(f"  [{score:.3f}] {doc.metadata['title'][:50]}...")
        print(f"         {doc.page_content[:80]}...")
