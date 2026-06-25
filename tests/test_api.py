"""测试 API 端点"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client():
    mock_pipeline = MagicMock()
    mock_pipeline.rag_retriever = MagicMock()
    mock_pipeline.get_stats.return_value = {
        "total_notes": 100, "total_chunks": 200,
        "domain_distribution": {"通识": 180},
    }
    mock_pipeline.chat.return_value = {
        "answer": "测试回答", "sources": [], "query": "测试问题",
    }

    mock_conv = MagicMock()
    mock_conv.create_session.return_value = "test-session-id"
    mock_conv.get_history.return_value = []
    mock_conv.rename_session.return_value = None
    mock_conv.archive_session.return_value = None
    mock_conv.restore_session.return_value = None
    mock_conv.list_sessions.return_value = []

    mock_cache = MagicMock()
    mock_cache.get.return_value = None

    with patch("src.api.app.SecondBrainPipeline", return_value=mock_pipeline), \
         patch("src.api.app.ConversationManager", return_value=mock_conv), \
         patch("src.api.app.load_model_config", return_value=None), \
         patch("src.api.app.RedisCache"), \
         patch("src.api.app.ResponseCache", return_value=mock_cache):
        from src.api.app import app

        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"


class TestStatsEndpoint:
    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        d = r.json()
        assert "total_notes" in d


class TestSessionEndpoints:
    def test_create_session(self, client):
        r = client.post("/api/v1/sessions")
        assert r.status_code == 200
        assert "session_id" in r.json()

    def test_list_sessions(self, client):
        r = client.get("/api/v1/sessions")
        assert r.status_code == 200

    def test_delete_session(self, client):
        r = client.delete("/api/v1/sessions/test-session-id")
        assert r.status_code == 200

    def test_list_sessions_supports_archived_filter(self, client):
        r = client.get("/api/v1/sessions?archived=true")
        assert r.status_code == 200

    def test_update_session_title(self, client):
        r = client.patch("/api/v1/sessions/test-session-id", json={"title": "项目复盘"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_update_session_rejects_empty_title(self, client):
        r = client.patch("/api/v1/sessions/test-session-id", json={"title": "   "})
        assert r.status_code == 400

    def test_archive_session(self, client):
        r = client.patch("/api/v1/sessions/test-session-id", json={"archived": True})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_restore_session(self, client):
        r = client.patch("/api/v1/sessions/test-session-id", json={"archived": False})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_get_session_messages_includes_sources(self, client, monkeypatch):
        from src.api import app as app_module

        sources = [{"title": "快速学习", "source": "/vault/快速学习.md", "score": 0.8}]
        mock_conv = MagicMock()
        mock_conv.get_history.return_value = [
            SimpleNamespace(
                role="assistant",
                content="回答内容",
                timestamp="2026-06-09T10:00:00",
                metadata={"sources": sources},
            )
        ]
        monkeypatch.setattr(app_module, "conv_manager", mock_conv)

        r = client.get("/api/v1/sessions/test-session-id/messages")

        assert r.status_code == 200
        assert r.json()["messages"][0]["sources"] == sources

    def test_get_session_messages_backfills_missing_sources(self, client, monkeypatch):
        from src.api import app as app_module

        mock_conv = MagicMock()
        mock_conv.get_history.return_value = [
            SimpleNamespace(
                role="user",
                content="如何快速学习新知识",
                timestamp="2026-06-09T10:00:00",
                metadata=None,
            ),
            SimpleNamespace(
                role="assistant",
                content="回答内容",
                timestamp="2026-06-09T10:00:01",
                metadata=None,
            ),
        ]
        mock_pipeline = MagicMock()
        mock_pipeline.config.default_top_k = 5
        mock_pipeline.config.default_rerank_top_k = 10
        mock_pipeline.config.bm25_weight = 0.3
        mock_pipeline.config.vector_weight = 0.7
        mock_pipeline.rag_retriever.retrieve.return_value = [
            (
                SimpleNamespace(
                    metadata={
                        "title": "快速学习",
                        "source_file": "/vault/快速学习.md",
                        "domain": "通识",
                    }
                ),
                0.8123,
            )
        ]
        monkeypatch.setattr(app_module, "conv_manager", mock_conv)
        monkeypatch.setattr(app_module, "pipeline", mock_pipeline)

        r = client.get("/api/v1/sessions/test-session-id/messages")

        assert r.status_code == 200
        assert r.json()["messages"][1]["sources"] == [
            {
                "title": "快速学习",
                "source": "/vault/快速学习.md",
                "domain": "通识",
                "score": 0.812,
            }
        ]


class TestChatEndpoint:
    def test_chat(self, client):
        r = client.post("/api/v1/chat", json={"query": "测试问题"})
        assert r.status_code == 200
        d = r.json()
        assert d["answer"] == "测试回答"
        assert d["session_id"] != ""

    def test_chat_with_session(self, client):
        r = client.post("/api/v1/chat", json={
            "query": "测试", "session_id": "test-session-id",
        })
        assert r.status_code == 200


class TestDomainsEndpoint:
    def test_domains(self, client):
        r = client.get("/api/v1/domains")
        assert r.status_code == 200
        assert "domains" in r.json()


class TestSyncWebhook:
    def test_sync_webhook_pulls_vault_and_rebuilds(self, client, monkeypatch):
        from src.api import app as app_module
        from src.utils.vault_git import GitSyncResult

        mock_pipeline = MagicMock()
        mock_pipeline.rebuild_index_from_vault.return_value = {
            "total_notes": 1,
            "total_chunks": 2,
            "domain_distribution": {"其他": 2},
        }
        monkeypatch.setattr(app_module, "pipeline", mock_pipeline)
        monkeypatch.setattr(app_module, "SYNC_WEBHOOK_SECRET", "")

        with patch("src.api.app.pull_vault", return_value=GitSyncResult(stdout="pulled")) as pull:
            r = client.post("/api/v1/sync/webhook", content=b"{}")

        assert r.status_code == 200
        assert r.json()["sync_output"] == "pulled"
        pull.assert_called_once()
        mock_pipeline.rebuild_index_from_vault.assert_called_once_with(incremental=True)


class TestFeedbackEndpoint:
    def test_feedback(self, client):
        r = client.post("/api/v1/feedback", json={
            "session_id": "s1", "query": "q", "rating": 1,
        })
        assert r.status_code == 200
