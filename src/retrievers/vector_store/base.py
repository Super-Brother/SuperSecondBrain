"""向量存储抽象层

定义统一的向量存储接口，支持：
- FAISS（本地单机，向后兼容）
- Milvus（分布式，元数据过滤，增量更新）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document


@dataclass
class SearchResult:
    """检索结果"""
    document: Document
    score: float


@dataclass
class VectorStoreConfig:
    """向量存储配置"""
    embedding_dim: int = 768
    metric_type: str = "COSINE"  # COSINE, L2, IP
    index_type: str = "FLAT"     # FLAT, IVF_FLAT, HNSW
    # Milvus 专用
    host: str = "localhost"
    port: int = 19530
    collection_name: str = "enterprise_kb"
    # 权限元数据字段
    enable_acl: bool = False
    acl_fields: list[str] | None = None  # ["department", "access_level"]


class VectorStore(ABC):
    """向量存储抽象基类"""

    def __init__(self, config: VectorStoreConfig = None):
        self.config = config or VectorStoreConfig()
        self.documents: list[Document] = []
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            import os
            model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
            self._embedder = SentenceTransformer(model_name)
        return self._embedder

    @abstractmethod
    def add_documents(
        self,
        documents: list[Document],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """添加文档（支持增量更新）"""
        pass

    @abstractmethod
    def delete_by_filter(self, filter_expr: str | dict) -> int:
        """按条件删除文档，返回删除数量"""
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        filter_expr: str | dict | None = None,
    ) -> list[SearchResult]:
        """向量检索，支持元数据过滤"""
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """保存索引到本地"""
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """从本地加载索引"""
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """获取存储统计"""
        pass

    def _compute_embeddings(self, texts: list[str]) -> list[list[float]]:
        import numpy as np
        embeddings = self.embedder.encode(texts, show_progress_bar=True, batch_size=64)
        return np.array(embeddings, dtype=np.float32).tolist()
