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

import faiss
import jieba
import numpy as np
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


class VectorRetriever:
    """FAISS 向量检索器"""

    def __init__(self, embedding_dim: int = None):
        self.embedding_dim = embedding_dim  # None 表示从模型自动推断
        self.index = None  # 延迟初始化
        self.documents: list[Document] = []
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
            self._embedder = SentenceTransformer(model_name)
        return self._embedder

    def build_index(self, documents: list[Document]):
        """构建向量索引"""
        self.documents = documents
        texts = [doc.page_content for doc in documents]

        print(f"[VectorRetriever] 正在对 {len(texts)} 个 chunks 做 Embedding...")
        embeddings = self.embedder.encode(texts, show_progress_bar=True, batch_size=64)
        embeddings = np.array(embeddings, dtype=np.float32)

        # 自动推断维度
        if self.embedding_dim is None:
            self.embedding_dim = embeddings.shape[1]
            print(f"[VectorRetriever] Embedding 维度: {self.embedding_dim}")

        # 归一化（用于余弦相似度）
        faiss.normalize_L2(embeddings)

        if self.index is None:
            self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.index.add(embeddings)
        print(f"[VectorRetriever] 索引构建完成，共 {self.index.ntotal} 个向量")

    def search(self, query: str, top_k: int = 10, domain: str | None = None) -> list[tuple[Document, float]]:
        """向量检索"""
        query_vec = self.embedder.encode([query])
        query_vec = np.array(query_vec, dtype=np.float32)
        faiss.normalize_L2(query_vec)

        # 如果需要领域过滤，扩大检索范围再过滤
        search_k = top_k * 5 if domain else top_k
        scores, indices = self.index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            doc = self.documents[idx]
            # 领域过滤
            if domain and doc.metadata.get("domain") != domain:
                continue
            results.append((doc, float(score)))
            if len(results) >= top_k:
                break

        return results

    def save(self, path: str):
        """保存索引"""
        os.makedirs(path, exist_ok=True)
        faiss.write_index(self.index, os.path.join(path, "faiss.index"))
        with open(os.path.join(path, "documents.pkl"), "wb") as f:
            pickle.dump(self.documents, f)

    def load(self, path: str):
        """加载索引"""
        self.index = faiss.read_index(os.path.join(path, "faiss.index"))
        with open(os.path.join(path, "documents.pkl"), "rb") as f:
            self.documents = pickle.load(f)
        print(f"[VectorRetriever] 加载索引完成，共 {self.index.ntotal} 个向量")


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

    def search(self, query: str, top_k: int = 10, domain: str | None = None) -> list[tuple[Document, float]]:
        """BM25 检索"""
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

        # 分别检索
        vector_results = self.vector.search(query, top_k=config.top_k, domain=config.domain_filter)
        bm25_results = self.bm25.search(query, top_k=config.top_k, domain=config.domain_filter)

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
            model_name = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
            self._reranker = CrossEncoder(model_name)
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
