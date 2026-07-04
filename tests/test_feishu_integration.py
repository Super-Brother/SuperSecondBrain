"""Tests for Feishu bot integration."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _message_payload(
    *,
    open_id: str = "ou_allowed",
    chat_type: str = "p2p",
    message_type: str = "text",
    content: str | dict = "企业知识库怎么接入？",
    message_id: str = "om_1",
):
    if isinstance(content, dict):
        encoded_content = json.dumps(content, ensure_ascii=False)
    else:
        encoded_content = json.dumps({"text": content}, ensure_ascii=False)

    return {
        "schema": "2.0",
        "header": {
            "event_id": f"evt_{message_id}",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant_1",
            "token": "verify-token",
        },
        "event": {
            "sender": {"sender_id": {"open_id": open_id, "user_id": "u_1"}},
            "message": {
                "message_id": message_id,
                "chat_id": "oc_group",
                "chat_type": chat_type,
                "message_type": message_type,
                "content": encoded_content,
            },
        },
    }


class RecordingFeishuClient:
    def __init__(self):
        self.replies = []
        self.reactions = []
        self.deleted_reactions = []

    def reply_to_message(self, message_id: str, text: str):
        self.replies.append({"message_id": message_id, "text": text})

    def add_message_reaction(self, message_id: str, emoji_type: str):
        reaction_id = f"reaction_{len(self.reactions) + 1}"
        self.reactions.append(
            {
                "message_id": message_id,
                "emoji_type": emoji_type,
                "reaction_id": reaction_id,
            }
        )
        return reaction_id

    def delete_message_reaction(self, message_id: str, reaction_id: str):
        self.deleted_reactions.append(
            {"message_id": message_id, "reaction_id": reaction_id}
        )


def _handler(allowed_open_ids="ou_allowed", rag_answer=None):
    from src.integrations.feishu import FeishuConfig, FeishuEventHandler

    client = RecordingFeishuClient()
    rag_calls = []
    audit_events = []

    def ask_knowledge(query, session_id, context):
        rag_calls.append(
            {"query": query, "session_id": session_id, "context": context}
        )
        if isinstance(rag_answer, Exception):
            raise rag_answer
        return rag_answer or {
            "answer": "推荐用飞书机器人适配层接入。",
            "sources": [
                {"title": "企业知识库方案", "source": "/vault/a.md"},
                {"title": "飞书机器人设计", "source": "/vault/b.md"},
                {"title": "MCP 第二阶段", "source": "/vault/c.md"},
                {"title": "不会展示第四条", "source": "/vault/d.md"},
            ],
        }

    def record_audit(details, status):
        audit_events.append({"details": details, "status": status})

    config = FeishuConfig(
        enabled=True,
        verification_token="verify-token",
        allowed_open_ids=frozenset(allowed_open_ids.split(","))
        if allowed_open_ids
        else frozenset(),
    )
    handler = FeishuEventHandler(
        config=config,
        client=client,
        ask_knowledge=ask_knowledge,
        audit_recorder=record_audit,
    )
    return handler, client, rag_calls, audit_events


def test_url_verification_returns_challenge():
    handler, _, _, _ = _handler()

    result = handler.handle_callback(
        {
            "type": "url_verification",
            "token": "verify-token",
            "challenge": "challenge-code",
        }
    )

    assert result.status_code == 200
    assert result.body == {"challenge": "challenge-code"}


def test_disabled_bot_rejects_events():
    from src.integrations.feishu import FeishuConfig, FeishuEventHandler

    client = RecordingFeishuClient()
    handler = FeishuEventHandler(
        config=FeishuConfig(enabled=False, verification_token="verify-token"),
        client=client,
        ask_knowledge=lambda query, session_id, context: {},
    )

    result = handler.handle_callback(_message_payload())

    assert result.status_code == 404
    assert result.body == {"error": "feishu bot disabled"}
    assert client.replies == []


def test_text_message_calls_rag_and_replies_with_sources():
    handler, client, rag_calls, audit_events = _handler()

    result = handler.handle_callback(_message_payload())

    assert result.status_code == 200
    assert result.body == {"status": "ok"}
    assert rag_calls == [
        {
            "query": "企业知识库怎么接入？",
            "session_id": "feishu:user:ou_allowed",
            "context": {
                "tenant_key": "tenant_1",
                "open_id": "ou_allowed",
                "user_id": "u_1",
                "chat_id": "oc_group",
                "message_id": "om_1",
                "chat_type": "p2p",
            },
        }
    ]
    assert client.reactions == [
        {
            "message_id": "om_1",
            "emoji_type": "THINKING",
            "reaction_id": "reaction_1",
        },
    ]
    assert client.deleted_reactions == [
        {"message_id": "om_1", "reaction_id": "reaction_1"},
    ]
    assert len(client.replies) == 1
    assert client.replies[0]["message_id"] == "om_1"
    assert "推荐用飞书机器人适配层接入。" in client.replies[0]["text"]
    assert "来源：" in client.replies[0]["text"]
    assert "/vault/a.md" in client.replies[0]["text"]
    assert "/vault/c.md" in client.replies[0]["text"]
    assert "/vault/d.md" not in client.replies[0]["text"]
    assert audit_events[-1]["status"] == "success"


def test_group_message_session_is_scoped_by_chat_and_user():
    handler, _, rag_calls, _ = _handler()

    result = handler.handle_callback(
        _message_payload(chat_type="group", message_id="om_group")
    )

    assert result.status_code == 200
    assert rag_calls[0]["session_id"] == "feishu:chat:oc_group:user:ou_allowed"


def test_duplicate_message_id_is_not_answered_twice():
    handler, client, rag_calls, _ = _handler()
    payload = _message_payload(message_id="om_duplicate")

    first = handler.handle_callback(payload)
    second = handler.handle_callback(payload)

    assert first.body == {"status": "ok"}
    assert second.body == {"status": "duplicate"}
    assert len(rag_calls) == 1
    assert len(client.replies) == 1


def test_non_allowed_user_is_rejected_without_rag_call():
    handler, client, rag_calls, audit_events = _handler(allowed_open_ids="ou_other")

    result = handler.handle_callback(_message_payload(open_id="ou_blocked"))

    assert result.status_code == 200
    assert result.body == {"status": "forbidden"}
    assert rag_calls == []
    assert client.replies == [
        {
            "message_id": "om_1",
            "text": "你暂无权限使用知识库机器人。请联系管理员开通。",
        }
    ]
    assert audit_events[-1]["status"] == "failure"
    assert audit_events[-1]["details"]["open_id"] == "ou_blocked"


def test_non_text_message_gets_fallback_reply():
    handler, client, rag_calls, _ = _handler()

    result = handler.handle_callback(
        _message_payload(message_type="image", content={"image_key": "img_1"})
    )

    assert result.status_code == 200
    assert result.body == {"status": "unsupported"}
    assert rag_calls == []
    assert client.replies == [
        {"message_id": "om_1", "text": "当前仅支持文本问题。"}
    ]


def test_rag_error_gets_safe_reply():
    handler, client, _, audit_events = _handler(rag_answer=RuntimeError("secret boom"))

    result = handler.handle_callback(_message_payload())

    assert result.status_code == 200
    assert result.body == {"status": "error"}
    assert client.reactions == [
        {
            "message_id": "om_1",
            "emoji_type": "THINKING",
            "reaction_id": "reaction_1",
        },
    ]
    assert client.deleted_reactions == [
        {"message_id": "om_1", "reaction_id": "reaction_1"},
    ]
    assert client.replies == [
        {"message_id": "om_1", "text": "知识库暂时不可用，请稍后再试。"},
    ]
    assert "secret boom" not in client.replies[0]["text"]
    assert audit_events[-1]["status"] == "failure"


@pytest.fixture
def api_client():
    from src.api import app as app_module

    mock_pipeline = MagicMock()
    mock_pipeline.rag_retriever = MagicMock()
    mock_pipeline.get_stats.return_value = {
        "total_notes": 1,
        "total_chunks": 1,
        "domain_distribution": {},
    }
    mock_conv = MagicMock()
    mock_conv.create_session.return_value = "test-session-id"
    mock_conv.get_history.return_value = []
    mock_cache = MagicMock()
    mock_cache.get.return_value = None

    with (
        patch.object(app_module, "SecondBrainPipeline", return_value=mock_pipeline),
        patch.object(app_module, "ConversationManager", return_value=mock_conv),
        patch.object(app_module, "load_model_config", return_value=None),
        patch.object(app_module, "RedisCache"),
        patch.object(app_module, "ResponseCache", return_value=mock_cache),
    ):
        with TestClient(app_module.app) as client:
            yield client, app_module


def test_fastapi_feishu_route_delegates_to_handler(api_client, monkeypatch):
    client, app_module = api_client

    class FakeHandler:
        def __init__(self):
            self.payload = None

        def handle_callback(self, payload):
            from src.integrations.feishu import FeishuCallbackResult

            self.payload = payload
            return FeishuCallbackResult(status_code=200, body={"status": "ok"})

    fake_handler = FakeHandler()
    monkeypatch.setattr(
        app_module,
        "create_feishu_handler",
        lambda request: fake_handler,
    )

    response = client.post(
        "/api/v1/integrations/feishu/events",
        json={"type": "url_verification", "challenge": "ok"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_handler.payload == {"type": "url_verification", "challenge": "ok"}


def test_fastapi_feishu_route_deduplicates_message_ids(api_client, monkeypatch):
    client, app_module = api_client
    feishu_client = RecordingFeishuClient()
    rag_calls = []

    monkeypatch.setenv("FEISHU_BOT_ENABLED", "true")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    monkeypatch.setenv("FEISHU_ALLOWED_OPEN_IDS", "ou_allowed")
    monkeypatch.setattr(app_module, "FeishuAPIClient", lambda config: feishu_client)

    def ask(query, session_id, context):
        rag_calls.append({"query": query, "session_id": session_id})
        return {"answer": "ok", "sources": []}

    monkeypatch.setattr(app_module, "_ask_knowledge_for_feishu", ask)
    payload = _message_payload(message_id="om_route_duplicate")

    first = client.post("/api/v1/integrations/feishu/events", json=payload)
    second = client.post("/api/v1/integrations/feishu/events", json=payload)

    assert first.status_code == 200
    assert first.json() == {"status": "ok"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(rag_calls) == 1
    assert feishu_client.reactions == [
        {
            "message_id": "om_route_duplicate",
            "emoji_type": "THINKING",
            "reaction_id": "reaction_1",
        },
    ]
    assert feishu_client.deleted_reactions == [
        {"message_id": "om_route_duplicate", "reaction_id": "reaction_1"},
    ]
    assert len(feishu_client.replies) == 1
