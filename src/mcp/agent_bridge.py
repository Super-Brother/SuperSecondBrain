"""Agent 调用桥接层。

把 MCP tools 封装为 Python 方法，供项目内部 Agent 或飞书机器人直接调用，
无需走 JSON-RPC/MCP 协议。
"""

from __future__ import annotations

from typing import Any

from src.mcp.context import KBContext
from src.mcp.tools import register_tools
from fastmcp import FastMCP


class KnowledgeBaseAgentBridge:
    """知识库 Agent 桥接：把 tools 暴露为普通 Python 方法。"""

    def __init__(self, ctx: KBContext):
        self.ctx = ctx
        self._mcp = FastMCP("secondbrain-agent-bridge")
        self._tools = register_tools(self._mcp, ctx)

    def _call(self, name: str, **kwargs) -> dict[str, Any]:
        """按名称调用内部 tool 函数。"""
        fn = self._tools.get(name)
        if fn is None:
            return {"success": False, "error": f"未知 tool: {name}"}
        return fn(**kwargs)

    def chat(self, query: str, **kwargs) -> dict[str, Any]:
        """基于知识库问答。"""
        return self._call("knowledge_base_chat", query=query, **kwargs)

    def search(self, query: str, **kwargs) -> dict[str, Any]:
        """检索笔记。"""
        return self._call("search_notes", query=query, **kwargs)

    def get_note(self, relative_path: str) -> dict[str, Any]:
        """获取单篇笔记。"""
        return self._call("get_note", relative_path=relative_path)

    def create_note(self, relative_path: str, title: str, **kwargs) -> dict[str, Any]:
        """创建笔记。"""
        return self._call("create_note", relative_path=relative_path, title=title, **kwargs)

    def update_note(self, relative_path: str, **kwargs) -> dict[str, Any]:
        """更新笔记。"""
        return self._call("update_note", relative_path=relative_path, **kwargs)

    def delete_note(self, relative_path: str) -> dict[str, Any]:
        """删除笔记。"""
        return self._call("delete_note", relative_path=relative_path)

    def upload_document(self, filename: str, content_base64: str, **kwargs) -> dict[str, Any]:
        """上传文档。"""
        return self._call("upload_document", filename=filename, content_base64=content_base64, **kwargs)

    def rebuild_index(self, incremental: bool = True) -> dict[str, Any]:
        """触发索引重建。"""
        return self._call("rebuild_index", incremental=incremental)

    def list_index_versions(self) -> dict[str, Any]:
        """列出索引版本。"""
        return self._call("list_index_versions")

    def switch_index_version(self, version_id: str) -> dict[str, Any]:
        """切换索引版本。"""
        return self._call("switch_index_version", version_id=version_id)

    def rollback_index(self) -> dict[str, Any]:
        """回滚索引版本。"""
        return self._call("rollback_index")

    def get_stats(self) -> dict[str, Any]:
        """获取知识库统计。"""
        return self._call("get_kb_stats")

    def list_domains(self) -> dict[str, Any]:
        """获取领域分布。"""
        return self._call("list_domains")
