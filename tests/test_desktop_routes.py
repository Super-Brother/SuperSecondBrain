"""测试桌面 API 路由"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("SECONDBRAIN_DESKTOP_MODE", raising=False)
    monkeypatch.delenv("SECONDBRAIN_USER_DATA_DIR", raising=False)

    mock_pipeline = MagicMock()
    mock_pipeline.rag_retriever = MagicMock()
    mock_pipeline.get_stats.return_value = {
        "total_notes": 100,
        "total_chunks": 200,
        "domain_distribution": {"通识": 180},
    }
    mock_pipeline.rebuild_index_from_vault.return_value = {
        "total_notes": 10,
        "total_chunks": 50,
    }

    mock_conv = MagicMock()
    mock_conv.create_session.return_value = "test-session-id"
    mock_conv.get_history.return_value = []
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


def test_desktop_status_returns_config(client):
    response = client.get("/api/v1/desktop/status")
    assert response.status_code == 200
    data = response.json()
    assert "onboarding_complete" in data
    assert data["desktop_mode"] is False


def test_desktop_config_round_trip(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    payload = {
        "vault_path": "/tmp/vault",
        "llm_base_url": "http://localhost:11434/v1",
        "llm_api_key": "not-needed",
        "llm_model": "qwen2.5:7b",
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "reranker_model": "BAAI/bge-reranker-base",
        "onboarding_complete": True,
    }
    response = client.post("/api/v1/desktop/config", json=payload)
    assert response.status_code == 200
    assert response.json()["config"]["llm_model"] == "qwen2.5:7b"


def test_desktop_import_data_copies_known_files(client, monkeypatch, tmp_path):
    target = tmp_path / "target"
    source = tmp_path / "source"
    source.mkdir()
    (source / "conversations.db").write_text("db", encoding="utf-8")
    (source / "index").mkdir()
    (source / "index" / "stats.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(target))

    response = client.post(
        "/api/v1/desktop/import-data",
        json={"source_data_dir": str(source), "overwrite": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert "conversations.db" in data["copied"]
    assert (target / "conversations.db").exists()
    assert (target / "index" / "stats.json").exists()


def test_desktop_import_data_rejects_missing_source(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/desktop/import-data",
        json={"source_data_dir": str(tmp_path / "missing"), "overwrite": True},
    )

    assert response.status_code == 400


def test_index_build_starts_task(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    response = client.post("/api/v1/index/build")
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] in {"queued", "running", "succeeded"}


def test_index_task_returns_task_state(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    start_response = client.post("/api/v1/index/build")
    task_id = start_response.json()["task_id"]

    response = client.get(f"/api/v1/index/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["task_id"] == task_id


def test_index_task_missing_returns_404(client):
    response = client.get("/api/v1/index/tasks/does-not-exist")
    assert response.status_code == 404
