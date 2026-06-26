"""MCP 服务端上下文。

把 pipeline、vault_path、conversation_manager 等运行时依赖打包，
避免 tools 直接依赖全局变量或形成循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


from src.utils.logger import log


@dataclass
class KBContext:
    """MCP tools 运行所需的上下文对象。"""

    pipeline: Any
    vault_path: str
    conv_manager: Any | None = None
    _pipeline_loaded: bool = False

    def require_pipeline(self):
        """要求 pipeline 已初始化，否则抛出可读异常。"""
        if self.pipeline is None:
            raise RuntimeError("Pipeline 未初始化，请先构建或加载索引")
        return self.pipeline

    def ensure_pipeline(self):
        """懒加载 pipeline；MCP server 启动时不应立即加载模型和索引。"""
        if self.pipeline is not None:
            return self.pipeline
        if self._pipeline_loaded:
            return None
        try:
            # 延迟导入，避免循环依赖
            from src.api.app import ensure_pipeline

            self.pipeline = ensure_pipeline()
            # 如果已有索引，自动加载，与 FastAPI lifespan 行为保持一致
            if self.pipeline is not None:
                import os

                index_dir = self.pipeline.config.index_dir
                if os.path.exists(os.path.join(index_dir, "faiss.index")):
                    self.pipeline.load_index(index_dir)
        except Exception as e:
            log.warning("Pipeline 懒加载失败: %s", e)
        self._pipeline_loaded = True
        return self.pipeline
