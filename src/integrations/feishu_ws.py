"""Feishu WebSocket long-connection worker."""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from typing import Any

from src.integrations.feishu import (
    AskKnowledge,
    AuditRecorder,
    FeishuAPIClient,
    FeishuConfig,
    FeishuEventHandler,
)
from src.utils.logger import log


class FeishuWsWorker:
    """Receive Feishu message events through the official SDK WebSocket client."""

    def __init__(
        self,
        *,
        config: FeishuConfig,
        client: FeishuAPIClient,
        ask_knowledge: AskKnowledge,
        audit_recorder: AuditRecorder | None = None,
        processed_message_ids: set[str] | None = None,
        sdk: Any | None = None,
        log_level: str = "INFO",
    ):
        self.config = config
        self.client = client
        self.ask_knowledge = ask_knowledge
        self.audit_recorder = audit_recorder
        self.processed_message_ids = processed_message_ids
        self.sdk = sdk
        self.log_level = log_level
        self._event_handler: FeishuEventHandler | None = None

    def start(self) -> None:
        if not self.config.enabled:
            raise RuntimeError("FEISHU_BOT_ENABLED must be true to start Feishu WS")
        if not self.config.app_id or not self.config.app_secret:
            raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

        sdk = self.sdk or importlib.import_module("lark_oapi")
        dispatcher = (
            sdk.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message)
            .build()
        )
        log_level = getattr(sdk.LogLevel, self.log_level, getattr(sdk.LogLevel, "INFO"))
        client = sdk.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=dispatcher,
            log_level=log_level,
        )
        log.info("启动飞书长连接客户端: app_id=%s", self.config.app_id)
        client.start()

    def _handle_message(self, event: Any) -> None:
        payload = self._event_to_payload(event)
        message = (payload.get("event") or {}).get("message") or {}
        sender = (payload.get("event") or {}).get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        log.info(
            "收到飞书长连接消息: message_id=%s chat_id=%s chat_type=%s message_type=%s open_id=%s",
            message.get("message_id", ""),
            message.get("chat_id", ""),
            message.get("chat_type", ""),
            message.get("message_type", ""),
            sender_id.get("open_id", ""),
        )
        self._get_event_handler().handle_callback(payload)

    def _event_to_payload(self, event: Any) -> dict[str, Any]:
        if isinstance(event, dict):
            return event
        sdk = self.sdk or importlib.import_module("lark_oapi")
        marshaled = sdk.JSON.marshal(event)
        if isinstance(marshaled, str):
            return json.loads(marshaled)
        return dict(marshaled)

    def _get_event_handler(self) -> FeishuEventHandler:
        if self._event_handler is None:
            # Long-connection events are authenticated at connection time by the SDK,
            # so HTTP callback verification token/encrypt key are intentionally blank.
            long_connection_config = replace(
                self.config,
                verification_token="",
                encrypt_key="",
            )
            self._event_handler = FeishuEventHandler(
                config=long_connection_config,
                client=self.client,
                ask_knowledge=self.ask_knowledge,
                audit_recorder=self.audit_recorder,
                processed_message_ids=self.processed_message_ids,
            )
        return self._event_handler
