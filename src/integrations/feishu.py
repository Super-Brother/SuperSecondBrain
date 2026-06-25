"""Feishu bot integration helpers.

This module keeps Feishu event parsing and reply formatting separate from the
core RAG pipeline so the knowledge service remains platform-neutral.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from src.utils.logger import log


class MessageIdContainer(Protocol):
    """支持 add 和 __contains__ 的消息去重容器协议。"""

    def __contains__(self, item: str) -> bool: ...
    def add(self, item: str) -> None: ...


AskKnowledge = Callable[[str, str, dict[str, Any]], dict[str, Any]]
AuditRecorder = Callable[[dict[str, Any], str], None]


@dataclass(frozen=True)
class FeishuConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""
    allowed_open_ids: frozenset[str] = field(default_factory=frozenset)
    api_base_url: str = "https://open.feishu.cn/open-apis"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"enabled={self.enabled}, "
            f"app_id={self.app_id!r}, "
            f"app_secret=***, "
            f"verification_token=***, "
            f"encrypt_key=***, "
            f"allowed_open_ids={self.allowed_open_ids!r}, "
            f"api_base_url={self.api_base_url!r})"
        )

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        allowed = frozenset(
            item.strip()
            for item in os.getenv("FEISHU_ALLOWED_OPEN_IDS", "").split(",")
            if item.strip()
        )
        enabled = os.getenv("FEISHU_BOT_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(
            enabled=enabled,
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
            encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
            allowed_open_ids=allowed,
            api_base_url=os.getenv(
                "FEISHU_API_BASE_URL", "https://open.feishu.cn/open-apis"
            ).rstrip("/"),
        )


@dataclass(frozen=True)
class FeishuCallbackResult:
    status_code: int
    body: dict[str, Any]


class FeishuAPIClient:
    """Small Feishu OpenAPI client for bot message replies."""

    def __init__(self, config: FeishuConfig):
        self.config = config
        self._tenant_access_token: str | None = None
        self._tenant_access_token_expire_at = 0.0
        self._token_lock = threading.Lock()

    def reply_to_message(self, message_id: str, text: str) -> None:
        token = self._get_tenant_access_token()
        url = f"{self.config.api_base_url}/im/v1/messages/{message_id}/reply"
        payload = {
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        self._post_json(
            url,
            payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _get_tenant_access_token(self) -> str:
        with self._token_lock:
            now = time.time()
            if self._tenant_access_token and now < self._tenant_access_token_expire_at:
                return self._tenant_access_token
            if not self.config.app_id or not self.config.app_secret:
                raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

            url = f"{self.config.api_base_url}/auth/v3/tenant_access_token/internal"
            data = self._post_json(
                url,
                {
                    "app_id": self.config.app_id,
                    "app_secret": self.config.app_secret,
                },
            )
            token = data.get("tenant_access_token")
            if not token:
                raise RuntimeError(f"Feishu token response missing token: {data}")
            expire = int(data.get("expire", 7200))
            self._tenant_access_token = token
            self._tenant_access_token_expire_at = now + max(expire - 300, 60)
            return token

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                **(headers or {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Feishu API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Feishu API request failed: {exc.reason}") from exc

        data = json.loads(body) if body else {}
        if data.get("code", 0) != 0:
            raise RuntimeError(f"Feishu API error: {data}")
        return data


class FeishuEventHandler:
    """Handle Feishu callback payloads and route text messages to RAG."""

    def __init__(
        self,
        *,
        config: FeishuConfig,
        client: FeishuAPIClient,
        ask_knowledge: AskKnowledge,
        audit_recorder: AuditRecorder | None = None,
        processed_message_ids: MessageIdContainer | None = None,
    ):
        self.config = config
        self.client = client
        self.ask_knowledge = ask_knowledge
        self.audit_recorder = audit_recorder
        self._processed_message_ids = (
            processed_message_ids if processed_message_ids is not None else set()
        )

    def handle_callback(self, payload: dict[str, Any]) -> FeishuCallbackResult:
        if not self.config.enabled:
            return FeishuCallbackResult(
                status_code=404, body={"error": "feishu bot disabled"}
            )

        if "encrypt" in payload:
            return FeishuCallbackResult(
                status_code=400,
                body={"error": "encrypted Feishu callbacks are not supported yet"},
            )

        if not self._verify_token(payload):
            return FeishuCallbackResult(status_code=401, body={"error": "unauthorized"})

        if payload.get("type") == "url_verification":
            return FeishuCallbackResult(
                status_code=200,
                body={"challenge": payload.get("challenge", "")},
            )

        header = payload.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return FeishuCallbackResult(status_code=200, body={"status": "ignored"})

        event = payload.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        context = self._build_context(header, message, sender_id)
        message_id = context["message_id"]

        if not message_id:
            return FeishuCallbackResult(
                status_code=400, body={"error": "missing message_id"}
            )
        if message_id in self._processed_message_ids:
            return FeishuCallbackResult(status_code=200, body={"status": "duplicate"})

        self._processed_message_ids.add(message_id)

        open_id = context["open_id"]
        if self.config.allowed_open_ids and open_id not in self.config.allowed_open_ids:
            self.client.reply_to_message(
                message_id,
                "你暂无权限使用知识库机器人。请联系管理员开通。",
            )
            self._record_audit(context, "failure")
            return FeishuCallbackResult(status_code=200, body={"status": "forbidden"})

        if message.get("message_type") != "text":
            self.client.reply_to_message(message_id, "当前仅支持文本问题。")
            self._record_audit(context, "success")
            return FeishuCallbackResult(status_code=200, body={"status": "unsupported"})

        query = self._extract_text(message.get("content", ""))
        if not query:
            self.client.reply_to_message(message_id, "请发送文本问题。")
            self._record_audit(context, "failure")
            return FeishuCallbackResult(status_code=200, body={"status": "empty"})

        session_id = self._session_id(context)
        try:
            result = self.ask_knowledge(query, session_id, context)
            answer = self._format_answer(result)
            self.client.reply_to_message(message_id, answer)
            self._record_audit({**context, "session_id": session_id}, "success")
        except Exception as exc:
            log.warning("Feishu knowledge reply failed: %s", exc)
            self.client.reply_to_message(message_id, "知识库暂时不可用，请稍后再试。")
            self._record_audit({**context, "session_id": session_id}, "failure")
            return FeishuCallbackResult(status_code=200, body={"status": "error"})

        return FeishuCallbackResult(status_code=200, body={"status": "ok"})

    def _verify_token(self, payload: dict[str, Any]) -> bool:
        expected = self.config.verification_token
        if not expected:
            return True
        actual = payload.get("token") or (payload.get("header") or {}).get("token")
        return actual == expected

    def _build_context(
        self,
        header: dict[str, Any],
        message: dict[str, Any],
        sender_id: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "tenant_key": header.get("tenant_key", ""),
            "open_id": sender_id.get("open_id", ""),
            "user_id": sender_id.get("user_id", ""),
            "chat_id": message.get("chat_id", ""),
            "message_id": message.get("message_id", ""),
            "chat_type": message.get("chat_type", ""),
        }

    def _session_id(self, context: dict[str, Any]) -> str:
        open_id = context["open_id"]
        if context.get("chat_type") == "p2p":
            return f"feishu:user:{open_id}"
        return f"feishu:chat:{context['chat_id']}:user:{open_id}"

    def _extract_text(self, content: str) -> str:
        try:
            data = json.loads(content) if content else {}
        except json.JSONDecodeError:
            return content.strip()
        return str(data.get("text", "")).strip()

    def _format_answer(self, result: dict[str, Any]) -> str:
        answer = str(result.get("answer", "")).strip()
        sources = result.get("sources") or []
        source_lines = []
        for index, source in enumerate(sources[:3], start=1):
            title = source.get("title") or "来源"
            path = source.get("source") or source.get("source_file") or ""
            if path:
                source_lines.append(f"{index}. {title} - {path}")
            else:
                source_lines.append(f"{index}. {title}")
        if source_lines:
            return f"{answer}\n\n来源：\n" + "\n".join(source_lines)
        return answer

    def _record_audit(self, details: dict[str, Any], status: str) -> None:
        if self.audit_recorder is None:
            return
        self.audit_recorder(details, status)
