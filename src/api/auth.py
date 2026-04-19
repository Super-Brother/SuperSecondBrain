"""API Key 认证中间件"""

import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


PUBLIC_PATHS = {"/health", "/", "/docs", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self.api_key = api_key or os.getenv("API_KEY", "")

    async def dispatch(self, request: Request, call_next):
        # 静态资源和健康检查免认证
        if not self.api_key or request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        if request.url.path.startswith("/assets"):
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key != self.api_key:
            return JSONResponse(status_code=401, content={"error": "Invalid API Key"})

        return await call_next(request)
