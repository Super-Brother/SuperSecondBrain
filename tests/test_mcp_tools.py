"""MCP tools 单元测试。

用 mock pipeline 和临时 vault 验证 tool 注册、调用和异常处理。
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from src.mcp.context import KBContext
from src.mcp.agent_bridge import KnowledgeBaseAgentBridge
from src.mcp.tools import register_tools


@pytest.fixture
def temp_vault(tmp_path: Path):
    """创建临时 vault 目录。"""
    vault = tmp_path / "vault"
    vault.mkdir()
    return str(vault)


@pytest.fixture
def mock_pipeline(temp_vault: str):
    """创建模拟的 SecondBrainPipeline。"""
    pipeline = MagicMock()
    pipeline.rag_retriever = MagicMock()

    pipeline.chat.return_value = {
        "query": "test",
        "answer": "test answer",
        "sources": [
            {
                "title": "Test Note",
                "source": "test.md",
                "folder": "",
                "domain": "general",
                "tags": [],
                "score": 0.95,
            }
        ],
    }

    pipeline.get_stats.return_value = {
        "total_notes": 10,
        "total_chunks": 50,
        "domain_distribution": {"general": 5, "ai-ml": 5},
    }

    version_manager = MagicMock()
    version_manager.list_versions.return_value = [
        {"version_id": "v1", "is_current": True, "size_mb": 1.0, "stats": {}},
        {"version_id": "v0", "is_current": False, "size_mb": 0.9, "stats": {}},
    ]
    version_manager.get_stats.return_value = {
        "current_version": "v1",
        "total_versions": 2,
        "max_versions": 5,
    }
    version_manager.switch_version.return_value = {"version": "v1", "previous": "v0"}
    version_manager.rollback.return_value = {"version": "v0", "previous": "v1"}
    pipeline.version_manager = version_manager

    pipeline.rebuild_index_from_vault.return_value = {
        "total_notes": 10,
        "total_chunks": 50,
    }

    pipeline.llm_generator = MagicMock()
    pipeline.llm_generator.get_usage_stats.return_value = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }

    return pipeline


@pytest.fixture
def ctx(mock_pipeline, temp_vault: str):
    """创建 MCP 上下文。"""
    return KBContext(pipeline=mock_pipeline, vault_path=temp_vault, conv_manager=None)


@pytest.fixture
def tools(ctx):
    """创建已注册 tools 的字典。"""
    mcp = FastMCP("test-secondbrain")
    return register_tools(mcp, ctx)


class TestMCPToolsRegistered:
    """验证 tools 已正确注册。"""

    def test_all_tools_registered(self, tools):
        expected_tools = {
            "knowledge_base_chat",
            "search_notes",
            "get_note",
            "create_note",
            "update_note",
            "delete_note",
            "upload_document",
            "rebuild_index",
            "list_index_versions",
            "switch_index_version",
            "rollback_index",
            "get_kb_stats",
            "list_domains",
        }
        registered = set(tools.keys())
        assert expected_tools.issubset(registered)


class TestKnowledgeBaseChat:
    """测试 knowledge_base_chat tool。"""

    def test_chat_returns_answer_and_sources(self, ctx, tools):
        fn = tools["knowledge_base_chat"]
        result = fn(query="什么是 RAG？")

        assert result["success"] is True
        assert result["answer"] == "test answer"
        assert len(result["sources"]) == 1
        ctx.pipeline.chat.assert_called_once()

    def test_chat_pipeline_not_ready(self, temp_vault: str):
        ctx_empty = KBContext(pipeline=None, vault_path=temp_vault)
        # 模拟无可用索引，避免自动加载真实 pipeline
        ctx_empty.ensure_pipeline = lambda: None
        mcp = FastMCP("test-empty")
        empty_tools = register_tools(mcp, ctx_empty)
        fn = empty_tools["knowledge_base_chat"]
        result = fn(query="test")

        assert result["success"] is False
        assert "Pipeline 未初始化" in result["error"]


class TestSearchNotes:
    """测试 search_notes tool。"""

    def test_search_aggregates_results(self, ctx, tools, mock_pipeline):
        # 模拟 retrieve 返回两个属于同一笔记的 chunks
        from langchain_core.documents import Document

        mock_pipeline.rag_retriever.retrieve.return_value = [
            (
                Document(
                    page_content="chunk one content",
                    metadata={
                        "relative_path": "notes/test.md",
                        "title": "Test",
                        "folder": "notes",
                        "domain": "general",
                        "tags": ["test"],
                    },
                ),
                0.9,
            ),
            (
                Document(
                    page_content="chunk two content",
                    metadata={
                        "relative_path": "notes/test.md",
                        "title": "Test",
                        "folder": "notes",
                        "domain": "general",
                        "tags": ["test"],
                    },
                ),
                0.85,
            ),
        ]

        fn = tools["search_notes"]
        result = fn(query="test", top_k=5)

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["results"][0]["matched_chunks"]) == 2


class TestNoteManagement:
    """测试笔记 CRUD tools。"""

    def test_create_and_get_note(self, ctx, tools):
        create_fn = tools["create_note"]
        get_fn = tools["get_note"]

        created = create_fn(
            relative_path="test/hello.md",
            title="Hello",
            content="World",
            tags=["demo"],
        )
        assert created["success"] is True

        fetched = get_fn(relative_path="test/hello.md")
        assert fetched["success"] is True
        assert fetched["note"]["title"] == "Hello"
        assert "demo" in fetched["note"]["tags"]

    def test_update_note(self, ctx, tools):
        create_fn = tools["create_note"]
        update_fn = tools["update_note"]
        get_fn = tools["get_note"]

        create_fn(relative_path="test/update.md", title="Title", content="Original")
        updated = update_fn(relative_path="test/update.md", content="Updated")
        assert updated["success"] is True

        fetched = get_fn(relative_path="test/update.md")
        assert "Updated" in fetched["note"]["content"]

    def test_delete_note(self, ctx, tools):
        create_fn = tools["create_note"]
        delete_fn = tools["delete_note"]
        get_fn = tools["get_note"]

        create_fn(relative_path="test/delete.md", title="Delete Me")
        deleted = delete_fn(relative_path="test/delete.md")
        assert deleted["success"] is True

        fetched = get_fn(relative_path="test/delete.md")
        assert fetched["success"] is False
        assert fetched["status_code"] == 404


class TestUploadDocument:
    """测试 upload_document tool。"""

    def test_upload_md_document(self, ctx, tools, mock_pipeline):
        content = "# Test Document\n\nThis is a test."
        b64 = base64.b64encode(content.encode()).decode()

        fn = tools["upload_document"]
        result = fn(filename="test.md", content_base64=b64, trigger_rebuild=True)

        assert result["success"] is True
        assert result["filename"] == "test.md"
        assert (Path(ctx.vault_path) / "uploads" / "test.md").exists()
        mock_pipeline.rebuild_index_from_vault.assert_called_once_with(incremental=True)

    def test_upload_unsupported_extension(self, ctx, tools):
        fn = tools["upload_document"]
        result = fn(filename="test.exe", content_base64="aGVsbG8=")

        assert result["success"] is False
        assert "不支持的文件类型" in result["error"]

    def test_upload_invalid_base64(self, ctx, tools):
        fn = tools["upload_document"]
        result = fn(filename="test.md", content_base64="not-valid-base64!!!")

        assert result["success"] is False
        assert "base64" in result["error"]


class TestIndexManagement:
    """测试索引管理 tools。"""

    def test_index_tools_lazy_load_pipeline(self, temp_vault: str, mock_pipeline):
        ctx = KBContext(pipeline=None, vault_path=temp_vault)
        ctx.ensure_pipeline = MagicMock(return_value=mock_pipeline)
        mcp = FastMCP("test-lazy-index")
        lazy_tools = register_tools(mcp, ctx)

        rebuild = lazy_tools["rebuild_index"](incremental=True)
        versions = lazy_tools["list_index_versions"]()
        switched = lazy_tools["switch_index_version"](version_id="v1")
        rolled_back = lazy_tools["rollback_index"]()

        assert rebuild["success"] is True
        assert versions["success"] is True
        assert switched["success"] is True
        assert rolled_back["success"] is True
        assert ctx.ensure_pipeline.call_count == 4

    def test_rebuild_index(self, ctx, tools, mock_pipeline):
        fn = tools["rebuild_index"]
        result = fn(incremental=True)

        assert result["success"] is True
        assert result["rebuild_stats"]["total_notes"] == 10
        mock_pipeline.rebuild_index_from_vault.assert_called_once_with(incremental=True)

    def test_list_index_versions(self, ctx, tools, mock_pipeline):
        fn = tools["list_index_versions"]
        result = fn()

        assert result["success"] is True
        assert result["current_version"] == "v1"
        assert len(result["versions"]) == 2

    def test_switch_index_version(self, ctx, tools, mock_pipeline):
        fn = tools["switch_index_version"]
        result = fn(version_id="v1")

        assert result["success"] is True
        mock_pipeline.version_manager.switch_version.assert_called_once_with("v1")
        mock_pipeline.load_index.assert_called_once()

    def test_rollback_index(self, ctx, tools, mock_pipeline):
        fn = tools["rollback_index"]
        result = fn()

        assert result["success"] is True
        assert result["version_id"] == "v0"
        mock_pipeline.load_index.assert_called_once()


class TestKBStats:
    """测试统计类 tools。"""

    def test_stats_tools_lazy_load_pipeline(self, temp_vault: str, mock_pipeline):
        ctx = KBContext(pipeline=None, vault_path=temp_vault)
        ctx.ensure_pipeline = MagicMock(return_value=mock_pipeline)
        mcp = FastMCP("test-lazy-stats")
        lazy_tools = register_tools(mcp, ctx)

        stats = lazy_tools["get_kb_stats"]()
        domains = lazy_tools["list_domains"]()

        assert stats["success"] is True
        assert domains["success"] is True
        assert ctx.ensure_pipeline.call_count == 2

    def test_get_kb_stats(self, ctx, tools, mock_pipeline):
        fn = tools["get_kb_stats"]
        result = fn()

        assert result["success"] is True
        assert result["stats"]["total_notes"] == 10
        assert result["token_usage"]["prompt_tokens"] == 100

    def test_list_domains(self, ctx, tools):
        fn = tools["list_domains"]
        result = fn()

        assert result["success"] is True
        assert "general" in result["domains"]


class TestAgentBridge:
    """测试 Agent 桥接层。"""

    def test_bridge_delegates_to_tools(self, ctx):
        bridge = KnowledgeBaseAgentBridge(ctx)
        result = bridge.chat(query="test")

        assert result["success"] is True
        assert result["answer"] == "test answer"

    def test_bridge_list_versions(self, ctx, mock_pipeline):
        bridge = KnowledgeBaseAgentBridge(ctx)
        result = bridge.list_index_versions()

        assert result["success"] is True
        assert result["current_version"] == "v1"
        mock_pipeline.version_manager.list_versions.assert_called_once()
