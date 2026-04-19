"""测试 API 端点"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client():
    with patch("src.api.app.pipeline") as mock_pipeline, \
         patch("src.api.app.conv_manager") as mock_conv:
        mock_pipeline.rag_retriever = MagicMock()
        mock_pipeline.get_stats.return_value = {
            "total_notes": 100, "total_chunks": 200,
            "domain_distribution": {"通识": 180},
        }
        mock_pipeline.chat.return_value = {
            "answer": "测试回答", "sources": [], "query": "测试问题",
        }
        mock_conv.create_session.return_value = "test-session-id"
        mock_conv.get_history.return_value = []

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


class TestFeedbackEndpoint:
    def test_feedback(self, client):
        r = client.post("/api/v1/feedback", json={
            "session_id": "s1", "query": "q", "rating": 1,
        })
        assert r.status_code == 200
