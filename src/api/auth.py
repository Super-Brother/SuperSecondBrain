"""认证系统 — 支持邮箱绑定、验证码、JWT Token

生产环境需配置 SMTP 环境变量：
- SMTP_HOST
- SMTP_PORT (默认 587)
- SMTP_USER
- SMTP_PASSWORD
- SMTP_FROM (默认 SMTP_USER)

开发模式：验证码打印到控制台
"""

import os
import hashlib
import secrets
import time
import re
import smtplib
import sqlite3
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()


PUBLIC_PATHS = {
    "/health", "/", "/docs", "/openapi.json",
    "/api/v1/auth/login", "/api/v1/auth/register",
    "/api/v1/auth/send-code", "/api/v1/auth/verify-code",
}

# ---- 内存存储（验证码临时性，不持久化） ----
_VERIFY_CODES = {}   # email -> {code, exp, purpose}


class UserStore:
    """SQLite 用户持久化存储"""

    def __init__(self, db_path: str = "data/auth.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                exp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tokens_exp ON tokens(exp);
        """)

    # ---- users ----

    def add_user(self, username: str, password_hash: str, salt: str, email: str):
        self.conn.execute(
            "INSERT INTO users (username, password_hash, salt, email, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, salt, email, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_user_by_username(self, username: str) -> dict | None:
        row = self.conn.execute(
            "SELECT username, password_hash, salt, email FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        row = self.conn.execute(
            "SELECT username, password_hash, salt, email FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(row) if row else None

    def user_exists(self, username: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row is not None

    def email_exists(self, email: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row is not None

    def has_any_user(self) -> bool:
        row = self.conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    # ---- tokens ----

    def add_token(self, token: str, username: str, email: str, exp: float):
        self.conn.execute(
            "INSERT INTO tokens (token, username, email, exp) VALUES (?, ?, ?, ?)",
            (token, username, email, exp),
        )
        self.conn.commit()

    def get_token(self, token: str) -> dict | None:
        row = self.conn.execute(
            "SELECT username, email, exp FROM tokens WHERE token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def delete_token(self, token: str):
        self.conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        self.conn.commit()

    def cleanup_expired_tokens(self):
        self.conn.execute("DELETE FROM tokens WHERE exp < ?", (time.time(),))
        self.conn.commit()


_user_store = UserStore()


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return hashed, salt


def _verify_password(password: str, hashed: str, salt: str) -> bool:
    new_hash, _ = _hash_password(password, salt)
    return secrets.compare_digest(new_hash, hashed)


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def _send_email(to_email: str, subject: str, body: str) -> bool:
    """发送邮件，开发模式打印到控制台"""
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        print(f"\n[SMTP DEV MODE] To: {to_email}\nSubject: {subject}\nBody:\n{body}\n")
        return True

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")
        from_addr = os.getenv("SMTP_FROM", user)

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, port) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP ERROR] {e}")
        return False


# ---- 验证码 ----

def send_verify_code(email: str, purpose: str = "register") -> bool:
    """发送邮箱验证码"""
    if not _is_valid_email(email):
        return False

    code = f"{secrets.randbelow(900000) + 100000}"  # 6位数字
    _VERIFY_CODES[email] = {
        "code": code,
        "exp": time.time() + 600,  # 10分钟过期
        "purpose": purpose,
    }

    subject = "SecondBrain Chat 验证码"
    body = f"你的验证码是：{code}\n\n10分钟内有效。如非本人操作，请忽略此邮件。"
    return _send_email(email, subject, body)


def verify_code(email: str, code: str, purpose: str = "register") -> bool:
    """验证邮箱验证码"""
    data = _VERIFY_CODES.get(email)
    if not data:
        return False
    if data["exp"] < time.time():
        return False
    if data["purpose"] != purpose:
        return False
    if not secrets.compare_digest(data["code"], code):
        return False
    # 验证成功后删除
    del _VERIFY_CODES[email]
    return True


# ---- Token ----

def create_token(username: str, email: str, expiry: int = 86400 * 7) -> str:
    token = secrets.token_urlsafe(32)
    _user_store.add_token(token, username, email, time.time() + expiry)
    _user_store.cleanup_expired_tokens()
    return token


def verify_token(token: str) -> dict | None:
    data = _user_store.get_token(token)
    if not data or data["exp"] < time.time():
        return None
    return data


# ---- 用户管理 ----

def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """注册用户，返回 (是否成功, 错误信息)"""
    if not username or len(username) < 3:
        return False, "用户名至少3个字符"
    if not _is_valid_email(email):
        return False, "邮箱格式不正确"
    if not password or len(password) < 6:
        return False, "密码至少6个字符"
    if _user_store.user_exists(username):
        return False, "用户名已存在"
    if _user_store.email_exists(email):
        return False, "邮箱已被注册"

    hashed, salt = _hash_password(password)
    _user_store.add_user(username, hashed, salt, email)
    return True, ""


def authenticate_user(login: str, password: str) -> tuple[bool, dict]:
    """验证用户（支持用户名或邮箱登录），返回 (是否成功, 用户信息)"""
    # 先按用户名查找
    user = _user_store.get_user_by_username(login)
    if not user and _is_valid_email(login):
        # 按邮箱查找
        user = _user_store.get_user_by_email(login)

    if not user:
        return False, {}
    if not _verify_password(password, user["password_hash"], user["salt"]):
        return False, {}

    return True, {"username": user["username"], "email": user["email"]}


def get_user_by_token(token: str) -> dict | None:
    data = verify_token(token)
    if not data:
        return None
    user = _user_store.get_user_by_username(data["username"])
    if not user:
        return None
    return {"username": data["username"], "email": user["email"]}


# ---- 中间件 ----

class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self.api_key = api_key or os.getenv("API_KEY", "")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not self.api_key and not _user_store.has_any_user():
            return await call_next(request)
        if path in PUBLIC_PATHS:
            return await call_next(request)
        if path.startswith("/assets"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key and api_key == self.api_key:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_data = verify_token(token)
            if user_data:
                request.state.user = user_data["username"]
                request.state.email = user_data["email"]
                return await call_next(request)

        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
