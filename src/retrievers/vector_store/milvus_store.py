"""Milvus 向量存储实现（企业级）"""

import os
import uuid
from datetime import datetime
from typing import Any

import numpy as np
from langchain_core.documents import Document

from src.retrievers.vector_store.base import VectorStore, VectorStoreConfig, SearchResult


class MilvusVectorStore(VectorStore):
    """Milvus 分布式向量存储，支持元数据过滤和增量更新"""

    def __init__(self, config: VectorStoreConfig = None):
        super().__init__(config)
        self.collection = None
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from pymilvus import MilvusClient
            self._client = MilvusClient(
                uri=f"http://{self.config.host}:{self.config.port}"
            )
        return self._client

    def _ensure_collection(self, dim: int = None):
        """确保集合存在"""
        from pymilvus import DataType

        dim = dim or self.config.embedding_dim
        name = self.config.collection_name

        if self.client.has_collection(name):
            self.collection = self.client.describe_collection(name)
            return

        # 创建集合
        schema = self.client.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="source_file", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="folder", datatype=DataType.VARCHAR, max_length=256)

        # 权限元数据字段
        if self.config.enable_acl:
            schema.add_field(field_name="department", datatype=DataType.ARRAY, element_type=DataType.VARCHAR, max_length=64, max_capacity=16)
            schema.add_field(field_name="access_level", datatype=DataType.INT32)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=self.config.index_type,
            metric_type=self.config.metric_type,
        )

        self.client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )
        self.collection = self.client.describe_collection(name)

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

        # 推断维度并创建集合
        dim = len(embeddings[0])
        self._ensure_collection(dim)

        entities = []
        for doc, emb in zip(documents, embeddings):
            entity = {
                "id": str(uuid.uuid4()),
                "vector": emb,
                "content": doc.page_content[:65535],
                "title": doc.metadata.get("title", "")[:512],
                "source_file": doc.metadata.get("source_file", "")[:512],
                "doc_id": doc.metadata.get("doc_id", doc.metadata.get("relative_path", str(uuid.uuid4())))[:128],
                "folder": doc.metadata.get("folder", "")[:256],
            }

            # 权限元数据
            if self.config.enable_acl:
                dept = doc.metadata.get("department", ["default"])
                if isinstance(dept, str):
                    dept = [dept]
                entity["department"] = dept[:16]
                entity["access_level"] = doc.metadata.get("access_level", 0)

            entities.append(entity)

        self.client.insert(
            collection_name=self.config.collection_name,
            data=entities,
        )
        self.documents.extend(documents)

    def delete_by_filter(self, filter_expr: str | dict) -> int:
        """按条件删除，支持 doc_id 精确删除或元数据过滤"""
        if isinstance(filter_expr, dict):
            # 构建 Milvus 过滤表达式
            conditions = []
            for key, value in filter_expr.items():
                if isinstance(value, list):
                    conditions.append(f"{key} in {value}")
                elif isinstance(value, str):
                    conditions.append(f'{key} == "{value}"')
                else:
                    conditions.append(f"{key} == {value}")
            filter_expr = " and ".join(conditions)

        result = self.client.delete(
            collection_name=self.config.collection_name,
            filter=filter_expr,
        )
        return result.get("delete_count", 0)

    def search(
        self,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        filter_expr: str | dict | None = None,
    ) -> list[SearchResult]:
        if query_embedding is None:
            if query_text is None:
                raise ValueError("query_embedding 或 query_text 必须提供一个")
            emb = self.embedder.encode([query_text])
            query_embedding = np.array(emb, dtype=np.float32).tolist()[0]

        # 转换过滤表达式
        expr = None
        if isinstance(filter_expr, dict):
            conditions = []
            for key, value in filter_expr.items():
                if isinstance(value, list):
                    conditions.append(f"{key} in {value}")
                elif isinstance(value, str):
                    conditions.append(f'{key} == "{value}"')
                else:
                    conditions.append(f"{key} == {value}")
            expr = " and ".join(conditions)
        elif isinstance(filter_expr, str):
            expr = filter_expr

        results = self.client.search(
            collection_name=self.config.collection_name,
            data=[query_embedding],
            filter=expr,
            limit=top_k,
            output_fields=["content", "title", "source_file", "doc_id", "folder"],
        )

        search_results = []
        for hits in results:
            for hit in hits:
                doc = Document(
                    page_content=hit["entity"]["content"],
                    metadata={
                        "title": hit["entity"]["title"],
                        "source_file": hit["entity"]["source_file"],
                        "doc_id": hit["entity"]["doc_id"],
                        "folder": hit["entity"]["folder"],
                    },
                )
                search_results.append(SearchResult(document=doc, score=hit["distance"]))

        return search_results

    def save(self, path: str) -> None:
        """Milvus 数据已持久化在服务端，本地只需保存配置"""
        import json
        os.makedirs(path, exist_ok=True)
        config_dict = {
            "host": self.config.host,
            "port": self.config.port,
            "collection_name": self.config.collection_name,
            "embedding_dim": self.config.embedding_dim,
            "metric_type": self.config.metric_type,
            "index_type": self.config.index_type,
            "enable_acl": self.config.enable_acl,
        }
        with open(os.path.join(path, "milvus_config.json"), "w") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> None:
        import json
        config_path = os.path.join(path, "milvus_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config_dict = json.load(f)
            self.config = VectorStoreConfig(**config_dict)
        self._ensure_collection()

    def get_stats(self) -> dict:
        stats = self.client.get_collection_stats(self.config.collection_name)
        return {
            "total_vectors": stats.get("row_count", 0),
            "collection": self.config.collection_name,
            "backend": "milvus",
        }
