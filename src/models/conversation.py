"""会话管理器 — 基于 SQLite 的多轮对话持久化"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str
    metadata: dict | None = None


class ConversationManager:
    def __init__(self, db_path: str = "data/conversations.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """)
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "metadata" not in columns:
            self.conn.execute("ALTER TABLE messages ADD COLUMN metadata TEXT")
            self.conn.commit()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
        self.conn.commit()
        return session_id

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[dict] = None):
        now = datetime.now().isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, metadata_json, now),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self.conn.commit()

    def get_history(self, session_id: str, limit: int = 20) -> list[Message]:
        rows = self.conn.execute(
            "SELECT role, content, metadata, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    def delete_session(self, session_id: str):
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()

    def list_sessions(self, limit: int = 50, include_empty: bool = True) -> list[dict]:
        """列出会话，默认保留空会话（新建对话后应立即可见）。"""
        sql = (
            "SELECT s.session_id, s.created_at, s.updated_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) as msg_count "
            "FROM sessions s "
        )
        if not include_empty:
            sql += "WHERE EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.session_id) "
        sql += "ORDER BY s.updated_at DESC LIMIT ?"
        rows = self.conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_message_count(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0

    def get_history_slice(self, session_id: str, offset: int = 0, limit: int = 20) -> list[Message]:
        rows = self.conn.execute(
            "SELECT role, content, metadata, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY timestamp ASC LIMIT ? OFFSET ?",
            (session_id, limit, offset),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        metadata = None
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = None
        return Message(
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
            metadata=metadata,
        )
