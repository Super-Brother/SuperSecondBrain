"""Tests for Feishu WebSocket long-connection worker."""

import json
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _message_payload():
    return {
        "schema": "2.0",
        "header": {
            "event_id": "evt_ws_1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant_1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_allowed", "user_id": "u_1"}},
            "message": {
                "message_id": "om_ws_1",
                "chat_id": "oc_group",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "长连接怎么配置？"}, ensure_ascii=False),
            },
        },
    }


class RecordingFeishuClient:
    def __init__(self):
        self.replies = []

    def reply_to_message(self, message_id: str, text: str):
        self.replies.append({"message_id": message_id, "text": text})


class FakeEventDispatcherBuilder:
    def __init__(self):
        self.message_handler = None

    def register_p2_im_message_receive_v1(self, handler):
        self.message_handler = handler
        return self

    def build(self):
        return SimpleNamespace(message_handler=self.message_handler)


class FakeEventDispatcherHandler:
    last_builder = None

    @classmethod
    def builder(cls, verification_token, encrypt_key):
        cls.last_builder = FakeEventDispatcherBuilder()
        cls.last_builder.verification_token = verification_token
        cls.last_builder.encrypt_key = encrypt_key
        return cls.last_builder


class FakeWsClient:
    instances = []

    def __init__(self, app_id, app_secret, *, event_handler, log_level=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.event_handler = event_handler
        self.log_level = log_level
        self.started = False
        FakeWsClient.instances.append(self)

    def start(self):
        self.started = True


class FakeJSON:
    @staticmethod
    def marshal(data):
        return json.dumps(data, ensure_ascii=False)


def _fake_sdk():
    FakeWsClient.instances.clear()
    FakeEventDispatcherHandler.last_builder = None
    return SimpleNamespace(
        EventDispatcherHandler=FakeEventDispatcherHandler,
        ws=SimpleNamespace(Client=FakeWsClient),
        JSON=FakeJSON,
        LogLevel=SimpleNamespace(INFO="INFO", DEBUG="DEBUG"),
    )


def test_ws_worker_registers_message_event_and_starts_client():
    from src.integrations.feishu import FeishuConfig
    from src.integrations.feishu_ws import FeishuWsWorker

    sdk = _fake_sdk()
    client = RecordingFeishuClient()
    rag_calls = []
    worker = FeishuWsWorker(
        config=FeishuConfig(
            enabled=True,
            app_id="cli_test",
            app_secret="secret",
            verification_token="http-only-token",
            allowed_open_ids=frozenset({"ou_allowed"}),
        ),
        client=client,
        ask_knowledge=lambda query, session_id, context: rag_calls.append(
            {"query": query, "session_id": session_id, "context": context}
        )
        or {"answer": "用长连接即可。", "sources": []},
        sdk=sdk,
    )

    worker.start()

    assert FakeWsClient.instances[0].app_id == "cli_test"
    assert FakeWsClient.instances[0].app_secret == "secret"
    assert FakeWsClient.instances[0].started is True
    assert FakeEventDispatcherHandler.last_builder.verification_token == ""
    assert FakeEventDispatcherHandler.last_builder.encrypt_key == ""

    FakeWsClient.instances[0].event_handler.message_handler(_message_payload())

    assert rag_calls == [
        {
            "query": "长连接怎么配置？",
            "session_id": "feishu:user:ou_allowed",
            "context": {
                "tenant_key": "tenant_1",
                "open_id": "ou_allowed",
                "user_id": "u_1",
                "chat_id": "oc_group",
                "message_id": "om_ws_1",
                "chat_type": "p2p",
            },
        }
    ]
    assert client.replies == [{"message_id": "om_ws_1", "text": "用长连接即可。"}]


def test_ws_worker_logs_received_event(caplog):
    from src.integrations.feishu import FeishuConfig
    from src.integrations.feishu_ws import FeishuWsWorker

    worker = FeishuWsWorker(
        config=FeishuConfig(enabled=True, app_id="cli_test", app_secret="secret"),
        client=RecordingFeishuClient(),
        ask_knowledge=lambda query, session_id, context: {
            "answer": "ok",
            "sources": [],
        },
        sdk=_fake_sdk(),
    )

    with caplog.at_level("INFO", logger="secondbrain"):
        worker._handle_message(_message_payload())

    assert "收到飞书长连接消息" in caplog.text
    assert "message_id=om_ws_1" in caplog.text
    assert "chat_type=p2p" in caplog.text
    assert "message_type=text" in caplog.text


def test_ws_worker_requires_enabled_app_id_and_secret():
    from src.integrations.feishu import FeishuConfig
    from src.integrations.feishu_ws import FeishuWsWorker

    worker = FeishuWsWorker(
        config=FeishuConfig(enabled=False),
        client=RecordingFeishuClient(),
        ask_knowledge=lambda query, session_id, context: {},
        sdk=_fake_sdk(),
    )

    with pytest.raises(RuntimeError, match="FEISHU_BOT_ENABLED"):
        worker.start()

    missing_secret = FeishuWsWorker(
        config=FeishuConfig(enabled=True, app_id="cli_test"),
        client=RecordingFeishuClient(),
        ask_knowledge=lambda query, session_id, context: {},
        sdk=_fake_sdk(),
    )

    with pytest.raises(RuntimeError, match="FEISHU_APP_ID and FEISHU_APP_SECRET"):
        missing_secret.start()


def test_worker_script_starts_sdk_outside_running_event_loop(monkeypatch):
    import scripts.feishu_ws_worker as worker_script

    loop_states = []
    lifespan_events = []

    class FakeLifespan:
        async def __aenter__(self):
            lifespan_events.append("entered")

        async def __aexit__(self, exc_type, exc, tb):
            lifespan_events.append("exited")

    class FakeAppModule:
        app = object()
        feishu_processed_message_ids = set()
        _ask_knowledge_for_feishu = staticmethod(lambda query, session_id, context: {})

        @staticmethod
        def lifespan(app):
            return FakeLifespan()

    class FakeWorker:
        def start(self):
            loop_states.append(asyncio.get_event_loop().is_running())

    monkeypatch.setattr(worker_script, "app_module", FakeAppModule)
    monkeypatch.setattr(worker_script, "build_worker", lambda: FakeWorker())

    worker_script.main()

    assert lifespan_events == ["entered", "exited"]
    assert loop_states == [False]


def test_worker_script_reads_log_level_from_env(monkeypatch):
    import scripts.feishu_ws_worker as worker_script

    captured = {}

    class FakeWorker:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("FEISHU_LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(worker_script, "FeishuWsWorker", FakeWorker)

    worker_script.build_worker()

    assert captured["log_level"] == "DEBUG"


def test_api_autostart_starts_feishu_ws_background_thread(monkeypatch):
    from src.api import app as app_module

    started = []

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon

        def is_alive(self):
            return False

        def start(self):
            started.append(
                {
                    "name": self.name,
                    "daemon": self.daemon,
                    "target": self.target,
                }
            )

    monkeypatch.setenv("FEISHU_WS_AUTOSTART", "true")
    monkeypatch.setenv("FEISHU_BOT_ENABLED", "true")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setattr(app_module, "feishu_ws_thread", None, raising=False)
    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    thread = app_module._start_feishu_ws_background()

    assert thread.name == "feishu-ws-worker"
    assert started[0]["name"] == "feishu-ws-worker"
    assert started[0]["daemon"] is True


def test_api_autostart_is_disabled_by_default(monkeypatch):
    from src.api import app as app_module

    monkeypatch.delenv("FEISHU_WS_AUTOSTART", raising=False)
    monkeypatch.setattr(app_module, "feishu_ws_thread", None, raising=False)

    assert app_module._start_feishu_ws_background() is None
