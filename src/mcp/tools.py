"""SecondBrain Chat MCP Tools。

把现有知识库能力封装为 12 个标准化 MCP tools：
- 问答：knowledge_base_chat
- 检索：search_notes, get_note
- 笔记管理：create_note, update_note, delete_note
- 文档管理：upload_document
- 索引管理：rebuild_index, list_index_versions, switch_index_version, rollback_index
- 元数据：get_kb_stats, list_domains

所有 tool 都通过 register_tools(mcp, ctx) 注册到 FastMCP 实例，
ctx 提供 pipeline、vault_path 等运行时依赖。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP

from src.mcp.context import KBContext
from src.utils.logger import log


def _format_http_error(e: Exception) -> dict[str, Any]:
    """把 FastAPI HTTPException 转成 MCP tool 可返回的错误结构。"""
    from fastapi import HTTPException

    if isinstance(e, HTTPException):
        return {
            "success": False,
            "error": e.detail,
            "status_code": e.status_code,
        }
    return {"success": False, "error": str(e)}


def _pipeline_not_ready() -> dict[str, Any]:
    return {
        "success": False,
        "error": "Pipeline 未初始化或索引未加载，请先构建索引",
    }


def register_tools(mcp: FastMCP, ctx: KBContext) -> dict[str, Callable]:
    """把知识库 tools 注册到 FastMCP 实例，返回 name -> function 映射。"""
    tools: dict[str, Callable] = {}

    # ---- 问答 ----

    @mcp.tool()
    def knowledge_base_chat(
        query: str,
        domain: str | None = None,
        top_k: int | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """基于知识库进行 RAG 问答，返回答案和来源引用。

        Args:
            query: 用户问题
            domain: 可选的领域过滤，如 "ai-ml" / "programming"
            top_k: 检索时返回的候选 chunk 数量，默认使用 pipeline 配置
            session_id: 多轮对话会话 ID，不传则创建新会话
        """
        pipeline = ctx.ensure_pipeline()
        if pipeline is None or pipeline.rag_retriever is None:
            return _pipeline_not_ready()

        try:
            from src.api.app import _get_history, _save_turn

            history = _get_history(session_id) if session_id else None
            result = pipeline.chat(query=query, domain=domain, top_k=top_k, history=history)

            if session_id:
                _save_turn(session_id, query, result.get("answer", ""), result.get("sources"))

            return {"success": True, **result}
        except Exception as e:
            log.exception("MCP knowledge_base_chat failed: %s", query)
            return {"success": False, "error": f"问答失败: {e}"}

    # ---- 检索 ----

    @mcp.tool()
    def search_notes(
        query: str,
        top_k: int = 20,
        domain: str | None = None,
    ) -> dict[str, Any]:
        """通过向量+BM25 混合检索搜索笔记，按 relative_path 聚合返回。

        Args:
            query: 检索关键词或问题
            top_k: 返回笔记数量上限
            domain: 可选的领域过滤
        """
        pipeline = ctx.ensure_pipeline()
        if pipeline is None or pipeline.rag_retriever is None:
            return _pipeline_not_ready()

        try:
            from src.api.notes import search_notes as _search_notes

            results = _search_notes(pipeline, query=query, top_k=top_k, domain_filter=domain)
            return {"success": True, "results": results, "count": len(results)}
        except Exception as e:
            log.exception("MCP search_notes failed: %s", query)
            return _format_http_error(e)

    @mcp.tool()
    def get_note(relative_path: str) -> dict[str, Any]:
        """获取单篇笔记/文档的完整内容与元数据。

        Args:
            relative_path: 相对于 vault 根目录的路径，如 "policies/ai-safety.md"
        """
        try:
            from src.api.notes import get_note as _get_note

            note = _get_note(ctx.vault_path, relative_path)
            return {"success": True, "note": note}
        except Exception as e:
            log.exception("MCP get_note failed: %s", relative_path)
            return _format_http_error(e)

    # ---- 笔记管理 ----

    @mcp.tool()
    def create_note(
        relative_path: str,
        title: str,
        content: str = "",
        tags: list[str] | None = None,
        date: str | None = None,
        frontmatter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """新建 Markdown 笔记。

        Args:
            relative_path: 笔记相对路径，必须以 .md 结尾
            title: 笔记标题
            content: 正文内容（Markdown）
            tags: 标签列表
            date: 日期字符串，如 "2026-06-26"
            frontmatter: 额外的 YAML frontmatter 字段
        """
        try:
            from src.api.notes import create_note as _create_note

            note = _create_note(
                vault_path=ctx.vault_path,
                relative_path=relative_path,
                title=title,
                content=content,
                tags=tags,
                date=date,
                frontmatter=frontmatter,
            )
            return {"success": True, "note": note}
        except Exception as e:
            log.exception("MCP create_note failed: %s", relative_path)
            return _format_http_error(e)

    @mcp.tool()
    def update_note(
        relative_path: str,
        content: str | None = None,
        tags: list[str] | None = None,
        date: str | None = None,
        frontmatter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """更新 Markdown 笔记。

        Args:
            relative_path: 笔记相对路径
            content: 新正文，None 表示保持原内容
            tags: 新标签列表，None 表示保持原标签
            date: 新日期，None 表示保持原日期
            frontmatter: 额外 frontmatter 字段，会与已有字段合并
        """
        try:
            from src.api.notes import update_note as _update_note

            note = _update_note(
                vault_path=ctx.vault_path,
                relative_path=relative_path,
                content=content,
                tags=tags,
                date=date,
                frontmatter=frontmatter,
            )
            return {"success": True, "note": note}
        except Exception as e:
            log.exception("MCP update_note failed: %s", relative_path)
            return _format_http_error(e)

    @mcp.tool()
    def delete_note(relative_path: str) -> dict[str, Any]:
        """删除笔记文件。

        Args:
            relative_path: 要删除的笔记相对路径
        """
        try:
            from src.api.notes import delete_note as _delete_note

            _delete_note(ctx.vault_path, relative_path)
            return {"success": True, "message": f"已删除 {relative_path}"}
        except Exception as e:
            log.exception("MCP delete_note failed: %s", relative_path)
            return _format_http_error(e)

    # ---- 文档管理 ----

    @mcp.tool()
    def upload_document(
        filename: str,
        content_base64: str,
        trigger_rebuild: bool = True,
    ) -> dict[str, Any]:
        """上传单个文档到知识库并可选触发增量索引。

        Args:
            filename: 文件名，必须带支持的后缀（.md/.pdf/.docx/.pptx/.xlsx）
            content_base64: 文件内容的 base64 编码
            trigger_rebuild: 是否立即触发增量索引重建
        """
        from src.parsers.document_router import PARSER_MAP

        ext = Path(filename).suffix.lower()
        if ext not in PARSER_MAP:
            return {
                "success": False,
                "error": f"不支持的文件类型: {ext}，支持: {list(PARSER_MAP.keys())}",
            }

        safe_name = Path(filename).name
        if safe_name.startswith(".") or "/" in safe_name or "\\" in safe_name:
            return {"success": False, "error": "非法文件名"}

        max_upload_size = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
        try:
            file_bytes = base64.b64decode(content_base64)
        except Exception as e:
            return {"success": False, "error": f"base64 解码失败: {e}"}

        if len(file_bytes) > max_upload_size:
            return {"success": False, "error": f"文件过大，最大 {max_upload_size // 1024 // 1024}MB"}

        vault_path = Path(ctx.vault_path)
        vault_path.mkdir(parents=True, exist_ok=True)
        upload_dir = vault_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / safe_name

        try:
            file_path.write_bytes(file_bytes)
        except Exception as e:
            return {"success": False, "error": f"保存文件失败: {e}"}

        rebuild_stats = None
        if trigger_rebuild:
            pipeline = ctx.ensure_pipeline()
            if pipeline is None:
                return {"success": False, "error": "Pipeline 未初始化，文件已保存但索引未重建"}
            try:
                rebuild_stats = pipeline.rebuild_index_from_vault(incremental=True)
            except Exception as e:
                log.exception("MCP upload_document rebuild failed")
                return {
                    "success": False,
                    "error": f"文件已保存，但索引重建失败: {e}",
                    "saved_path": str(file_path.relative_to(vault_path)),
                }

        return {
            "success": True,
            "filename": safe_name,
            "saved_path": str(file_path.relative_to(vault_path)),
            "rebuild_stats": rebuild_stats,
        }

    # ---- 索引管理 ----

    @mcp.tool()
    def rebuild_index(incremental: bool = True) -> dict[str, Any]:
        """触发索引重建。

        Args:
            incremental: True 为增量重建（只处理变更文档），False 为全量重建
        """
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            if incremental:
                stats = pipeline.rebuild_index_from_vault(incremental=True)
            else:
                stats = pipeline.rebuild_index_from_vault()
            return {"success": True, "rebuild_stats": stats}
        except Exception as e:
            log.exception("MCP rebuild_index failed")
            return {"success": False, "error": f"索引重建失败: {e}"}

    @mcp.tool()
    def list_index_versions() -> dict[str, Any]:
        """列出所有索引版本及当前激活版本。"""
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            versions = pipeline.version_manager.list_versions()
            stats = pipeline.version_manager.get_stats()
            return {
                "success": True,
                "current_version": stats["current_version"],
                "total_versions": stats["total_versions"],
                "max_versions": stats["max_versions"],
                "versions": versions,
            }
        except Exception as e:
            log.exception("MCP list_index_versions failed")
            return {"success": False, "error": f"列出索引版本失败: {e}"}

    @mcp.tool()
    def switch_index_version(version_id: str) -> dict[str, Any]:
        """切换到指定的索引版本。

        Args:
            version_id: 要切换的版本 ID
        """
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            result = pipeline.version_manager.switch_version(version_id)
            pipeline.load_index()
            return {
                "success": True,
                "version_id": version_id,
                "previous": result.get("previous"),
            }
        except Exception as e:
            log.exception("MCP switch_index_version failed: %s", version_id)
            return {"success": False, "error": f"切换索引版本失败: {e}"}

    @mcp.tool()
    def rollback_index() -> dict[str, Any]:
        """回滚到上一个索引版本。"""
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            result = pipeline.version_manager.rollback()
            pipeline.load_index()
            return {
                "success": True,
                "version_id": result["version"],
                "previous": result.get("previous"),
            }
        except Exception as e:
            log.exception("MCP rollback_index failed")
            return {"success": False, "error": f"回滚索引版本失败: {e}"}

    # ---- 元数据 ----

    @mcp.tool()
    def get_kb_stats() -> dict[str, Any]:
        """获取知识库统计信息，包括文档数、chunk 数、领域分布等。"""
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            stats = pipeline.get_stats()
            token_usage = {}
            if pipeline.llm_generator:
                token_usage = pipeline.llm_generator.get_usage_stats()
            return {
                "success": True,
                "stats": stats,
                "token_usage": token_usage,
            }
        except Exception as e:
            log.exception("MCP get_kb_stats failed")
            return {"success": False, "error": f"获取统计失败: {e}"}

    @mcp.tool()
    def list_domains() -> dict[str, Any]:
        """列出知识库中的领域分布。"""
        pipeline = ctx.ensure_pipeline()
        if pipeline is None:
            return _pipeline_not_ready()

        try:
            domains = pipeline.get_stats().get("domain_distribution", {})
            return {"success": True, "domains": domains}
        except Exception as e:
            log.exception("MCP list_domains failed")
            return {"success": False, "error": f"获取领域分布失败: {e}"}

    tools.update(
        {
            "knowledge_base_chat": knowledge_base_chat,
            "search_notes": search_notes,
            "get_note": get_note,
            "create_note": create_note,
            "update_note": update_note,
            "delete_note": delete_note,
            "upload_document": upload_document,
            "rebuild_index": rebuild_index,
            "list_index_versions": list_index_versions,
            "switch_index_version": switch_index_version,
            "rollback_index": rollback_index,
            "get_kb_stats": get_kb_stats,
            "list_domains": list_domains,
        }
    )
    return tools
