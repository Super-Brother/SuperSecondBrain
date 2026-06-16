"""FAISS 向量存储实现（向后兼容）"""

import os
import pickle
from pathlib import Path

import faiss
import numpy as np
from langchain_core.documents import Document

from src.retrievers.vector_store.base import VectorStore, VectorStoreConfig, SearchResult


class FAISSVectorStore(VectorStore):
    """FAISS 本地向量存储，完全兼容原有实现"""

    def __init__(self, config: VectorStoreConfig = None):
        super().__init__(config)
        self.index = None
        self.embedding_dim = config.embedding_dim if config else 768

    def add_documents(
        self,
        documents: list[Document],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        if not documents:
            return

        if embeddings is None:
            texts = [doc.page_content for doc in documents]
            embeddings = self._compute_embeddings(texts)

        embeddings = np.array(embeddings, dtype=np.float32)

        # L2 归一化用于余弦相似度
        faiss.normalize_L2(embeddings)

        if self.index is None:
            actual_dim = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(actual_dim)

        self.index.add(embeddings)
        self.documents.extend(documents)

    def remove_documents_by_relative_paths(self, relative_paths: set[str]) -> int:
        """按 relative_path 删除文档并重建 FAISS index

        FAISS IndexFlatIP 不支持直接删除，因此导出全部 embeddings 后，
        保留未删除的向量并重新创建 index。

        Args:
            relative_paths: 要删除的 relative_path 集合

        Returns:
            实际删除的文档数量
        """
        if not relative_paths or not self.documents:
            return 0

        keep_indices = [
            i
            for i, doc in enumerate(self.documents)
            if doc.metadata.get("relative_path", "") not in relative_paths
        ]
        removed_count = len(self.documents) - len(keep_indices)
        if removed_count == 0:
            return 0

        self.documents = [self.documents[i] for i in keep_indices]

        if self.index is not None and self.index.ntotal > 0:
            # IndexFlatIP 支持 reconstruct_n；导出全部 embeddings 后保留需要的
            all_embeddings = self.index.reconstruct_n(0, self.index.ntotal)
            keep_embeddings = all_embeddings[keep_indices]
            dim = self.index.d
            self.index = faiss.IndexFlatIP(dim)
            if len(keep_embeddings) > 0:
                self.index.add(keep_embeddings)

        return removed_count

    def delete_by_filter(self, filter_expr: str | dict) -> int:
        """FAISS 不支持直接删除，返回 0 提示重建索引"""
        return 0

    def search(
        self,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        filter_expr: str | dict | None = None,
    ) -> list[SearchResult]:
        if self.index is None or self.index.ntotal == 0:
            return []

        if query_embedding is None:
            if query_text is None:
                raise ValueError("query_embedding 或 query_text 必须提供一个")
            emb = self.embedder.encode([query_text])
            query_embedding = np.array(emb, dtype=np.float32)
        else:
            query_embedding = np.array([query_embedding], dtype=np.float32)

        faiss.normalize_L2(query_embedding)

        # 如果需要过滤，扩大检索范围
        search_k = top_k * 5 if filter_expr else top_k
        scores, indices = self.index.search(query_embedding, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]

            # 简单元数据过滤（内存过滤）
            if filter_expr and isinstance(filter_expr, dict):
                match = True
                for key, value in filter_expr.items():
                    if doc.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            results.append(SearchResult(document=doc, score=float(score)))
            if len(results) >= top_k:
                break

        return results

    def save(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        faiss.write_index(self.index, os.path.join(path, "faiss.index"))
        with open(os.path.join(path, "documents.pkl"), "wb") as f:
            pickle.dump(self.documents, f)

    def load(self, path: str) -> None:
        self.index = faiss.read_index(os.path.join(path, "faiss.index"))
        with open(os.path.join(path, "documents.pkl"), "rb") as f:
            self.documents = pickle.load(f)

    def get_stats(self) -> dict:
        return {
            "total_vectors": self.index.ntotal if self.index else 0,
            "total_documents": len(self.documents),
            "backend": "faiss",
        }
