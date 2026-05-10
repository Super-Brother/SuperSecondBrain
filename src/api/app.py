"""FastAPI 应用入口"""

import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig
from src.models.conversation import ConversationManager
from src.utils.logger import log
from src.utils.cache import ResponseCache
from src.utils.redis_cache import RedisCache
from src.api.auth import APIKeyMiddleware
from src.api.static import HTML_TEMPLATE
from src.utils.vault_watcher import VaultWatcher

# ---- 配置 ----

VAULT_PATH = os.getenv(
    "VAULT_PATH",
    "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
)
INDEX_DIR = os.getenv("INDEX_DIR", "data/index")

# ---- 全局状态 ----

pipeline: SecondBrainPipeline = None
conv_manager: ConversationManager = None
response_cache: ResponseCache = None
vault_watcher: VaultWatcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, conv_manager, response_cache, vault_watcher

    config = PipelineConfig(
        vault_path=VAULT_PATH,
        index_dir=INDEX_DIR,
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", "not-needed"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:3b"),
    )
    pipeline = SecondBrainPipeline(config)
    conv_manager = ConversationManager()
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        response_cache = RedisCache(redis_url=redis_url, ttl_seconds=int(os.getenv("CACHE_TTL", "3600")))
        log.info("Redis 缓存已启用: %s", redis_url)
    else:
        response_cache = ResponseCache(max_size=256, ttl_seconds=int(os.getenv("CACHE_TTL", "3600")))

    index_path = Path(INDEX_DIR)
    if (index_path / "faiss.index").exists():
        log.info("加载已有索引: %s", INDEX_DIR)
        pipeline.load_index(INDEX_DIR)
    else:
        log.warning("未找到索引，请运行: python scripts/build_index.py")

    # 启动 Vault 自动同步
    auto_sync = os.getenv("AUTO_SYNC", "false").lower() in ("true", "1", "yes")
    if auto_sync:
        debounce = float(os.getenv("AUTO_SYNC_DEBOUNCE", "5.0"))
        vault_watcher = VaultWatcher(VAULT_PATH, pipeline, debounce_seconds=debounce)
        try:
            vault_watcher.start()
        except FileNotFoundError:
            log.warning("Vault 路径不存在，自动同步未启动: %s", VAULT_PATH)

    yield

    # 清理
    if vault_watcher is not None:
        vault_watcher.stop()


# ---- App ----

app = FastAPI(
    title="SecondBrain Chat API",
    description="基于 RAG 的个人知识库智能问答系统",
    version="0.2.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("API_KEY", "")
if api_key:
    app.add_middleware(APIKeyMiddleware, api_key=api_key)
    log.info("API Key 认证已启用")


# ---- 请求计时中间件 ----

@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    latency = (time.time() - start) * 1000
    log.info("%s %s → %d (%.0fms)", request.method, request.url.path, response.status_code, latency)
    return response


# ---- 数据模型 ----

class ChatRequest(BaseModel):
    query: str
    domain: str | None = None
    top_k: int | None = None
    stream: bool = False
    session_id: str | None = None


class ChatResponse(BaseModel):
    query: str
    answer: str
    sources: list[dict]
    session_id: str


class ModelSwitchRequest(BaseModel):
    preset: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float = 0.3


class SessionResponse(BaseModel):
    session_id: str


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    rating: int  # 1=好评, -1=差评
    comment: str | None = None


class LoginRequest(BaseModel):
    login: str  # 用户名或邮箱
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    verify_code: str


class SendCodeRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


# ---- 辅助 ----

def _get_history(session_id: str | None) -> list[dict] | None:
    if not session_id or conv_manager is None:
        return None
    messages = conv_manager.get_history(session_id)
    if not messages:
        return None
    history = [{"role": m.role, "content": m.content} for m in messages]
    # 多轮对话压缩：超过 20 条时，对前面的消息生成摘要
    if len(history) > 20 and pipeline and pipeline.llm_generator:
        early = history[:-10]  # 保留最近 10 条完整
        try:
            summary = pipeline.llm_generator.summarize_conversation(early)
            if summary:
                return [{"role": "system", "content": f"历史对话摘要：{summary}"}] + history[-10:]
        except Exception:
            pass
    return history


def _save_turn(session_id: str, query: str, answer: str):
    if not session_id or conv_manager is None:
        return
    conv_manager.add_message(session_id, "user", query)
    conv_manager.add_message(session_id, "assistant", answer)


# ---- API ----

@app.get("/health")
async def health_check():
    if pipeline is None:
        return {"status": "starting", "index_loaded": False}
    result = {
        "status": "ok",
        "index_loaded": pipeline.rag_retriever is not None,
        "stats": pipeline.get_stats(),
    }
    if vault_watcher is not None:
        result["auto_sync"] = vault_watcher.stats
    else:
        result["auto_sync"] = {"is_running": False}
    return result


@app.get("/stats")
async def get_stats():
    if pipeline is None:
        return {"error": "服务未就绪"}
    stats = pipeline.get_stats()
    # 附加 token 使用统计
    if pipeline.llm_generator:
        stats["token_usage"] = pipeline.llm_generator.get_usage_stats()
    stats["cache_size"] = response_cache.size if response_cache else 0
    return stats


@app.post("/api/v1/sessions", response_model=SessionResponse)
async def create_session():
    return SessionResponse(session_id=conv_manager.create_session())


@app.get("/api/v1/sessions")
async def list_sessions(limit: int = 50):
    return {"sessions": conv_manager.list_sessions(limit=limit)}


@app.delete("/api/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    conv_manager.delete_session(session_id)
    return {"status": "ok"}


@app.post("/api/v1/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    if pipeline is None or pipeline.rag_retriever is None:
        return ChatResponse(
            query=body.query,
            answer="知识库索引未加载，请先构建索引。",
            sources=[],
            session_id=body.session_id or "",
        )

    session_id = body.session_id or conv_manager.create_session()

    # 查缓存
    cached = response_cache.get(body.query, body.domain) if response_cache else None
    if cached:
        log.info("缓存命中: %s", body.query[:30])
        _save_turn(session_id, body.query, cached["answer"])
        return ChatResponse(**cached, session_id=session_id)

    history = _get_history(session_id)
    result = pipeline.chat(
        query=body.query,
        domain=body.domain,
        top_k=body.top_k,
        history=history,
    )

    _save_turn(session_id, body.query, result["answer"])

    # 写缓存
    if response_cache:
        response_cache.put(body.query, result, body.domain)

    return ChatResponse(**result, session_id=session_id)


@app.post("/api/v1/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(request: Request, body: ChatRequest):
    if pipeline is None or pipeline.rag_retriever is None:
        async def error_stream():
            yield "data: " + json.dumps({"error": "知识库索引未加载"}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    session_id = body.session_id or conv_manager.create_session()
    history = _get_history(session_id)

    async def generate():
        full_answer = ""
        async for chunk in pipeline.chat_stream(
            query=body.query,
            domain=body.domain,
            top_k=body.top_k,
            history=history,
        ):
            if chunk.startswith("__SOURCES__:"):
                sources_json = chunk.replace("__SOURCES__:", "").strip()
                yield f"data: {json.dumps({'type': 'sources', 'data': json.loads(sources_json)}, ensure_ascii=False)}\n\n"
            else:
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'answer', 'content': chunk}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        _save_turn(session_id, request.query, full_answer)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/domains")
async def list_domains():
    if pipeline is None:
        return {"error": "服务未就绪"}
    return {"domains": pipeline.get_stats().get("domain_distribution", {})}


@app.post("/api/v1/feedback")
async def submit_feedback(request: FeedbackRequest):
    log.info("反馈: session=%s rating=%d query=%s", request.session_id, request.rating, request.query[:30])
    return {"status": "ok"}


@app.get("/api/v1/models")
async def list_models():
    """获取可用模型列表和当前配置"""
    from src.models.llm_generator import LLMGenerator
    return LLMGenerator.get_available_models()


@app.post("/api/v1/models/switch")
async def switch_model(request: ModelSwitchRequest):
    """切换 LLM 模型配置"""
    from src.models.llm_generator import PRESET_MODELS, LLMConfig

    if request.preset and request.preset in PRESET_MODELS:
        preset = PRESET_MODELS[request.preset]
        llm_config = LLMConfig(
            base_url=preset["base_url"],
            api_key=preset["api_key"],
            model=preset["model"],
            temperature=request.temperature,
        )
    else:
        llm_config = LLMConfig(
            base_url=request.base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=request.api_key or os.getenv("LLM_API_KEY", "not-needed"),
            model=request.model or os.getenv("LLM_MODEL", "qwen2.5:3b"),
            temperature=request.temperature,
        )

    if pipeline is None:
        return {"error": "Pipeline 未初始化"}

    result = pipeline.switch_llm(llm_config)
    log.info("模型切换: model=%s base_url=%s", llm_config.model, llm_config.base_url)
    return result


@app.post("/api/v1/auth/send-code")
@limiter.limit("3/minute")
async def send_code(request: Request, body: SendCodeRequest):
    """发送邮箱验证码"""
    from src.api.auth import send_verify_code
    ok = send_verify_code(body.email, "register")
    if not ok:
        return JSONResponse(status_code=400, content={"error": "邮箱格式不正确或发送失败"})
    return {"status": "ok", "message": "验证码已发送"}


@app.post("/api/v1/auth/verify-code")
async def verify_email_code(request: VerifyCodeRequest):
    """验证邮箱验证码（可选，注册时会自动验证）"""
    from src.api.auth import verify_code
    ok = verify_code(request.email, request.code, "register")
    if not ok:
        return JSONResponse(status_code=400, content={"error": "验证码错误或已过期"})
    return {"status": "ok"}


@app.post("/api/v1/auth/register")
async def register(request: RegisterRequest):
    """注册（需要邮箱验证码）"""
    from src.api.auth import verify_code, register_user, create_token

    # 验证邮箱验证码
    if not verify_code(request.email, request.verify_code, "register"):
        return JSONResponse(status_code=400, content={"error": "验证码错误或已过期"})

    ok, error = register_user(request.username, request.email, request.password)
    if not ok:
        return JSONResponse(status_code=400, content={"error": error})

    token = create_token(request.username, request.email)
    return {"token": token, "username": request.username, "email": request.email}


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """登录（支持用户名或邮箱）"""
    from src.api.auth import authenticate_user, create_token

    ok, user_info = authenticate_user(request.login, request.password)
    if not ok:
        return JSONResponse(status_code=401, content={"error": "用户名/邮箱或密码错误"})

    token = create_token(user_info["username"], user_info["email"])
    return {"token": token, "username": user_info["username"], "email": user_info["email"]}


@app.get("/api/v1/auth/me")
async def me(request: Request):
    from src.api.auth import get_user_by_token
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "未登录"})
    user = get_user_by_token(auth[7:])
    if not user:
        return JSONResponse(status_code=401, content={"error": "Token 已过期"})
    return {"username": user["username"], "email": user["email"]}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
