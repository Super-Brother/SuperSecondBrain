"""向量存储模块

提供统一的向量存储接口，支持 FAISS（本地）和 Milvus（分布式）。

Usage:
    from src.retrievers.vector_store import VectorStore, FAISSVectorStore, MilvusVectorStore

    # FAISS 本地存储
    store = FAISSVectorStore()

    # Milvus 企业级存储
    config = VectorStoreConfig(
        host="localhost",
        port=19530,
        collection_name="my_kb",
        enable_acl=True,
    )
    store = MilvusVectorStore(config)
"""

from src.retrievers.vector_store.base import VectorStore, VectorStoreConfig, SearchResult
from src.retrievers.vector_store.faiss_store import FAISSVectorStore
from src.retrievers.vector_store.milvus_store import MilvusVectorStore

__all__ = [
    "VectorStore",
    "VectorStoreConfig",
    "SearchResult",
    "FAISSVectorStore",
    "MilvusVectorStore",
]
