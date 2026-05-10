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
import ssl
from email.mime.text import MIMEText
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


PUBLIC_PATHS = {
    "/health", "/", "/docs", "/openapi.json",
    "/api/v1/auth/login", "/api/v1/auth/register",
    "/api/v1/auth/send-code", "/api/v1/auth/verify-code",
}

# ---- 内存存储（生产环境应使用 Redis + 数据库） ----
_USERS = {}          # username -> {password_hash, salt, email}
_EMAIL_MAP = {}      # email -> username
_VERIFY_CODES = {}   # email -> {code, exp, purpose}
_TOKENS = {}         # token -> {username, email, exp}


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
    _TOKENS[token] = {"username": username, "email": email, "exp": time.time() + expiry}
    return token


def verify_token(token: str) -> dict | None:
    data = _TOKENS.get(token)
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
    if username in _USERS:
        return False, "用户名已存在"
    if email in _EMAIL_MAP:
        return False, "邮箱已被注册"

    hashed, salt = _hash_password(password)
    _USERS[username] = {
        "password_hash": hashed,
        "salt": salt,
        "email": email,
    }
    _EMAIL_MAP[email] = username
    return True, ""


def authenticate_user(login: str, password: str) -> tuple[bool, dict]:
    """验证用户（支持用户名或邮箱登录），返回 (是否成功, 用户信息)"""
    # 先按用户名查找
    user = _USERS.get(login)
    if not user and _is_valid_email(login):
        # 按邮箱查找
        username = _EMAIL_MAP.get(login)
        if username:
            user = _USERS.get(username)
            login = username

    if not user:
        return False, {}
    if not _verify_password(password, user["password_hash"], user["salt"]):
        return False, {}

    return True, {"username": login, "email": user["email"]}


def get_user_by_token(token: str) -> dict | None:
    data = verify_token(token)
    if not data:
        return None
    user = _USERS.get(data["username"])
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

        if not self.api_key and not _USERS:
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
