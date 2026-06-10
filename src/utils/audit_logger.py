"""审计日志模块 — SQLite 持久化

记录所有敏感操作：chat, upload, sync, model_switch, login, register, feedback

Usage:
    from src.utils.audit_logger import audit_log, AuditAction
    audit_log(AuditAction.CHAT, request, details={"query": "..."}, status="success")
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import Request

from src.utils.logger import log


class AuditAction(str, Enum):
    """审计操作类型"""

    CHAT = "chat"
    CHAT_STREAM = "chat_stream"
    UPLOAD = "upload"
    SYNC = "sync"
    MODEL_SWITCH = "model_switch"
    LOGIN = "login"
    REGISTER = "register"
    FEEDBACK = "feedback"
    NOTE_CREATE = "note_create"
    NOTE_UPDATE = "note_update"
    NOTE_DELETE = "note_delete"
    NOTE_SEARCH = "note_search"


@dataclass
class AuditLogEntry:
    """审计日志条目"""

    id: str
    timestamp: str
    action: str
    user_id: str | None
    user_email: str | None
    ip: str | None
    user_agent: str | None
    details: str
    status: str


class AuditLogger:
    """审计日志记录器（SQLite 后端）"""

    def __init__(self, db_path: str = "data/audit.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化审计日志表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    user_id TEXT,
                    user_email TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    details TEXT,
                    status TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_logs(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_action
                ON audit_logs(action)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_logs(user_id)
            """)

    def log(
        self,
        action: AuditAction,
        request: Request | None,
        details: dict[str, Any] | None = None,
        status: str = "success",
    ) -> str | None:
        """记录一条审计日志

        Args:
            action: 操作类型
            request: FastAPI Request 对象（提取 IP、User-Agent、用户信息）
            details: 操作详情字典（会被 JSON 序列化）
            status: 操作状态（success / failure / error）

        Returns:
            日志 ID，如果记录失败则返回 None
        """
        try:
            import json

            log_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            # 从 request 提取信息
            ip = None
            user_agent = None
            user_id = None
            user_email = None

            if request is not None:
                # IP 优先取 X-Forwarded-For（代理场景），否则直接取 client
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    ip = forwarded.split(",")[0].strip()
                else:
                    ip = request.client.host if request.client else None

                user_agent = request.headers.get("User-Agent")

                # 认证用户信息
                if hasattr(request.state, "user") and request.state.user:
                    user_id = request.state.user
                if hasattr(request.state, "email") and request.state.email:
                    user_email = request.state.email

            details_json = json.dumps(details, ensure_ascii=False) if details else "{}"

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO audit_logs
                    (id, timestamp, action, user_id, user_email, ip, user_agent, details, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (log_id, now, action.value, user_id, user_email, ip, user_agent, details_json, status),
                )

            return log_id
        except Exception as e:
            log.warning("审计日志记录失败: %s", e)
            return None

    def query(
        self,
        action: AuditAction | None = None,
        user_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """查询审计日志"""
        conditions = []
        params = []
        if action:
            conditions.append("action = ?")
            params.append(action.value)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM audit_logs
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()

        return [
            AuditLogEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                action=r["action"],
                user_id=r["user_id"],
                user_email=r["user_email"],
                ip=r["ip"],
                user_agent=r["user_agent"],
                details=r["details"],
                status=r["status"],
            )
            for r in rows
        ]


# 全局实例（懒加载）
_audit_logger_instance: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志记录器"""
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger()
    return _audit_logger_instance


def audit_log(
    action: AuditAction,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
    status: str = "success",
) -> str | None:
    """便捷函数：记录审计日志"""
    logger = get_audit_logger()
    return logger.log(action, request, details, status)
