"""FastAPI 应用入口"""

import faulthandler
import os

# macOS MPS 内存分配器在模型预热时可能触发段错误，完全禁用 MPS 避免崩溃
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

faulthandler.enable()

# 关键：在 jieba 等多线程库之前先初始化 torch，
# 避免 PyTorch 线程状态与 jieba 多线程冲突导致的段错误 (macOS)
import torch  # noqa: F401

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# 在国内服务器部署时，强制使用 HuggingFace 镜像，避免模型下载被墙
import os
if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from fastapi import FastAPI, File, Request, UploadFile
from fastapi import status as http_status

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig
from src.retrievers.rag_retriever import SearchConfig
from src.models.conversation import ConversationManager
from src.utils.logger import log
from src.utils.cache import ResponseCache
from src.utils.redis_cache import RedisCache
from src.api.auth import APIKeyMiddleware
from src.api.static import HTML_TEMPLATE
from src.api.notes_routes import router as notes_router
from src.utils.vault_watcher import VaultWatcher
from src.utils.model_config_store import (
    StoredModelConfig,
    load_config as load_model_config,
    save_config as save_model_config,
)
from src.utils.metrics import get_metrics
from src.utils.audit_logger import audit_log, AuditAction
from src.utils.circuit_breaker import CircuitBreakerOpen

# slowapi 存储后端：优先 Redis，否则内存
redis_url = os.getenv("REDIS_URL")
if redis_url:
    try:
        from limits.storage import RedisStorage
        storage = RedisStorage(redis_url)
        limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
        log.info("slowapi 使用 Redis 存储后端")
    except Exception as e:
        log.warning("slowapi Redis 存储初始化失败，回退到内存: %s", e)
        limiter = Limiter(key_func=get_remote_address)
else:
    limiter = Limiter(key_func=get_remote_address)

# ---- 配置 ----

VAULT_PATH = os.getenv(
    "VAULT_PATH",
    "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
)
INDEX_DIR = os.getenv("INDEX_DIR", "data/index")

# 同步配置
SYNC_WEBHOOK_SECRET = os.getenv("SYNC_WEBHOOK_SECRET", "")
SYNC_SCRIPT_PATH = os.getenv("SYNC_SCRIPT_PATH", "")

# 文件上传限制
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

# ---- 全局状态 ----

pipeline: SecondBrainPipeline = None
conv_manager: ConversationManager = None
response_cache: ResponseCache = None
vault_watcher: VaultWatcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, conv_manager, response_cache, vault_watcher

    # 优先使用持久化的模型配置；不存在则回退到环境变量
    stored = load_model_config()
    if stored:
        llm_base_url = stored.base_url
        llm_api_key = stored.api_key or "not-needed"
        llm_model = stored.model
        log.info("加载持久化模型配置: model=%s base_url=%s", llm_model, llm_base_url)
    else:
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        llm_api_key = os.getenv("LLM_API_KEY", "not-needed")
        llm_model = os.getenv("LLM_MODEL", "qwen2.5:3b")

    config = PipelineConfig(
        vault_path=VAULT_PATH,
        index_dir=INDEX_DIR,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )
    pipeline = SecondBrainPipeline(config)
    conv_manager = ConversationManager()
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            response_cache = RedisCache(
                redis_url=redis_url,
                ttl_seconds=int(os.getenv("CACHE_TTL", "3600")),
            )
            log.info("Redis 缓存已启用: %s", redis_url)
        except Exception as e:
            log.warning("Redis 缓存连接失败，回退到内存缓存: %s", e)
            response_cache = ResponseCache(max_size=256, ttl_seconds=int(os.getenv("CACHE_TTL", "3600")))
    else:
        response_cache = ResponseCache(max_size=256, ttl_seconds=int(os.getenv("CACHE_TTL", "3600")))

    index_path = Path(INDEX_DIR)
    if (index_path / "faiss.index").exists():
        log.info("加载已有索引: %s", INDEX_DIR)
        pipeline.load_index(INDEX_DIR)
        # 预热模型（避免首次请求时加载导致的长时间等待）
        log.info("正在预热模型（Reranker / Embedding / LLM）...")
        pipeline.warmup()
        log.info("预热完成，服务就绪")
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

# 始终启用认证中间件（解析 Bearer token 注入 request.state.user，供审计日志使用）
# 仅在 API_KEY 环境变量设置时才强制校验 X-API-Key
api_key = os.getenv("API_KEY", "")
app.add_middleware(APIKeyMiddleware, api_key=api_key)
if api_key:
    log.info("API Key 认证已启用")

# 注册笔记管理路由
app.include_router(notes_router, prefix="/api/v1")


# ---- 请求计时中间件 ----

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求计时与增强日志中间件

    生成 X-Request-ID，记录延迟、IP、User-Agent、用户身份和 Metrics。
    """
    metrics = get_metrics()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    start = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start) * 1000

    # 提取客户端信息
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "-")
    user_agent = request.headers.get("User-Agent", "-")
    user = getattr(request.state, "user", None) or "-"

    # Metrics 记录
    metrics.record_latency("request", latency_ms)
    status_bucket = f"request_{response.status_code // 100}xx"
    metrics.increment(status_bucket)

    # 结构化日志
    log.info(
        "[%s] %s %s → %d (%.0fms) | ip=%s user=%s ua=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
        client_ip,
        user,
        user_agent[:50],
    )

    # 响应头中返回 Request-ID
    response.headers["X-Request-ID"] = request_id
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


class WebhookPayload(BaseModel):
    ref: str | None = None
    repository: dict | None = None
    commits: list | None = None


class SyncTriggerRequest(BaseModel):
    incremental: bool = True


# ---- 辅助 ----

def _get_history(session_id: str | None) -> list[dict] | None:
    if not session_id or conv_manager is None:
        return None
    # 获取更大的历史范围，确保压缩逻辑有机会触发
    messages = conv_manager.get_history(session_id, limit=100)
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
        except CircuitBreakerOpen:
            # 熔断器打开时，降级为返回最近 20 条完整历史
            log.warning("摘要熔断器已打开，降级为返回最近 20 条历史")
            return history[-20:]
        except Exception:
            pass
    return history


def _save_turn(session_id: str, query: str, answer: str, sources: list[dict] | None = None):
    if not session_id or conv_manager is None:
        return
    conv_manager.add_message(session_id, "user", query)
    metadata = {"sources": sources} if sources else None
    conv_manager.add_message(session_id, "assistant", answer, metadata=metadata)


def _sources_for_query(query: str) -> list[dict]:
    if not query or pipeline is None or pipeline.rag_retriever is None:
        return []
    try:
        config = SearchConfig(
            top_k=pipeline.config.default_top_k,
            rerank_top_k=pipeline.config.default_rerank_top_k,
            bm25_weight=pipeline.config.bm25_weight,
            vector_weight=pipeline.config.vector_weight,
        )
        results = pipeline.rag_retriever.retrieve(query, config)
    except Exception:
        return []
    return [
        {
            "title": doc.metadata.get("title", ""),
            "source": doc.metadata.get("source_file", ""),
            "domain": doc.metadata.get("domain", ""),
            "score": round(score, 3),
        }
        for doc, score in results
    ]


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
    # 附加 Metrics 汇总
    metrics = get_metrics()
    stats["metrics"] = metrics.get_summary()
    return stats


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus 指标导出端点（text exposition format）"""
    from fastapi.responses import PlainTextResponse
    metrics = get_metrics()
    return PlainTextResponse(content=metrics.to_prometheus(), media_type="text/plain")


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


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定会话的历史消息"""
    if conv_manager is None:
        return JSONResponse(status_code=503, content={"error": "服务未就绪"})
    messages = conv_manager.get_history(session_id, limit=100)
    serialized = []
    last_user_query = None
    for m in messages:
        sources = (m.metadata or {}).get("sources", [])
        if m.role == "assistant" and not sources and last_user_query:
            sources = _sources_for_query(last_user_query)
        serialized.append(
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "sources": sources,
            }
        )
        if m.role == "user":
            last_user_query = m.content

    return {
        "session_id": session_id,
        "messages": serialized,
    }


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
        _save_turn(session_id, body.query, cached["answer"], cached.get("sources"))
        return ChatResponse(**cached, session_id=session_id)

    history = _get_history(session_id)
    result = pipeline.chat(
        query=body.query,
        domain=body.domain,
        top_k=body.top_k,
        history=history,
    )

    _save_turn(session_id, body.query, result["answer"], result.get("sources"))

    # 写缓存
    if response_cache:
        response_cache.put(body.query, result, body.domain)

    # 审计日志
    audit_log(
        AuditAction.CHAT,
        request,
        details={"query": body.query[:200], "domain": body.domain, "session_id": session_id},
        status="success",
    )

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

    # 流式请求审计日志（请求开始时记录）
    audit_log(
        AuditAction.CHAT_STREAM,
        request,
        details={"query": body.query[:200], "domain": body.domain, "session_id": session_id},
        status="success",
    )

    async def generate():
        full_answer = ""
        sources = []
        async for chunk in pipeline.chat_stream(
            query=body.query,
            domain=body.domain,
            top_k=body.top_k,
            history=history,
        ):
            if chunk.startswith("__SOURCES__:"):
                sources_json = chunk.replace("__SOURCES__:", "").strip()
                sources = json.loads(sources_json)
                yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
            else:
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'answer', 'content': chunk}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        _save_turn(session_id, body.query, full_answer, sources)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/domains")
async def list_domains():
    if pipeline is None:
        return {"error": "服务未就绪"}
    return {"domains": pipeline.get_stats().get("domain_distribution", {})}


# ---- 索引版本管理 ----

@app.get("/api/v1/index/versions")
async def list_index_versions():
    """列出所有索引版本"""
    if pipeline is None:
        return {"error": "服务未就绪"}
    try:
        versions = pipeline.version_manager.list_versions()
        stats = pipeline.version_manager.get_stats()
        return {
            "current_version": stats["current_version"],
            "total_versions": stats["total_versions"],
            "max_versions": stats["max_versions"],
            "versions": versions,
        }
    except Exception as e:
        return {"error": str(e)}


class SwitchVersionRequest(BaseModel):
    version_id: str


@app.post("/api/v1/index/switch")
async def switch_index_version(request: Request, body: SwitchVersionRequest):
    """切换到指定索引版本（原子切换，服务不中断）"""
    if pipeline is None:
        return JSONResponse(status_code=503, content={"error": "服务未就绪"})
    try:
        result = pipeline.version_manager.switch_version(body.version_id)
        # 重新加载索引
        pipeline.load_index()
        audit_log(
            AuditAction.MODEL_SWITCH,  # 复用 model_switch 动作，或新增 INDEX_SWITCH
            request,
            details={"version_id": body.version_id, "previous": result.get("previous")},
            status="success",
        )
        return {
            "status": "ok",
            "version_id": body.version_id,
            "previous": result.get("previous"),
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/v1/index/rollback")
async def rollback_index_version(request: Request):
    """回滚到上一个索引版本"""
    if pipeline is None:
        return JSONResponse(status_code=503, content={"error": "服务未就绪"})
    try:
        result = pipeline.version_manager.rollback()
        pipeline.load_index()
        audit_log(
            AuditAction.MODEL_SWITCH,
            request,
            details={"version_id": result["version"], "action": "rollback"},
            status="success",
        )
        return {
            "status": "ok",
            "version_id": result["version"],
            "previous": result.get("previous"),
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/v1/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest):
    log.info("反馈: session=%s rating=%d query=%s", body.session_id, body.rating, body.query[:30])
    audit_log(
        AuditAction.FEEDBACK,
        request,
        details={"session_id": body.session_id, "rating": body.rating, "query": body.query[:200]},
        status="success",
    )
    return {"status": "ok"}


@app.get("/api/v1/models")
async def list_models():
    """获取可用模型列表和当前配置（基于 pipeline 实际生效配置 + 持久化文件）"""
    from src.models.llm_generator import PRESET_MODELS

    # 优先用 pipeline 当前生效配置；持久化文件提供 preset 标识
    stored = load_model_config()
    if pipeline and pipeline.config:
        current_base_url = pipeline.config.llm_base_url
        current_model = pipeline.config.llm_model
        current_temperature = pipeline.config.llm_temperature
    else:
        current_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        current_model = os.getenv("LLM_MODEL", "qwen2.5:3b")
        current_temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # 反向查找 preset key（如果当前配置匹配某个预设）
    preset_key = stored.preset if stored else None
    if not preset_key:
        for key, val in PRESET_MODELS.items():
            if val["base_url"] == current_base_url and val["model"] == current_model:
                preset_key = key
                break
        else:
            preset_key = "custom"

    return {
        "presets": {
            key: {"name": val["name"], "model": val["model"], "base_url": val["base_url"]}
            for key, val in PRESET_MODELS.items()
        },
        "current": {
            "preset": preset_key,
            "base_url": current_base_url,
            "api_key": "***" if (stored and stored.api_key) else "",
            "model": current_model,
            "temperature": current_temperature,
        },
    }


@app.post("/api/v1/models/switch")
async def switch_model(request: ModelSwitchRequest):
    """切换 LLM 模型配置（运行时生效 + 落盘持久化）"""
    from src.models.llm_generator import PRESET_MODELS, LLMConfig

    if request.preset and request.preset in PRESET_MODELS:
        preset = PRESET_MODELS[request.preset]
        llm_config = LLMConfig(
            base_url=preset["base_url"],
            api_key=preset["api_key"],
            model=preset["model"],
            temperature=request.temperature,
        )
        preset_key = request.preset
    else:
        llm_config = LLMConfig(
            base_url=request.base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=request.api_key or os.getenv("LLM_API_KEY", "not-needed"),
            model=request.model or os.getenv("LLM_MODEL", "qwen2.5:3b"),
            temperature=request.temperature,
        )
        preset_key = "custom"

    if pipeline is None:
        return {"error": "Pipeline 未初始化"}

    result = pipeline.switch_llm(llm_config)

    # 持久化：刷新页面或重启服务后仍生效
    save_model_config(StoredModelConfig(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key or "",
        model=llm_config.model,
        temperature=llm_config.temperature,
        preset=preset_key,
    ))

    log.info("模型切换并持久化: preset=%s model=%s base_url=%s", preset_key, llm_config.model, llm_config.base_url)
    audit_log(
        AuditAction.MODEL_SWITCH,
        request,
        details={"preset": preset_key, "model": llm_config.model, "base_url": llm_config.base_url},
        status="success",
    )
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
async def register(request: Request, body: RegisterRequest):
    """注册（需要邮箱验证码）"""
    from src.api.auth import verify_code, register_user, create_token

    # 验证邮箱验证码
    if not verify_code(body.email, body.verify_code, "register"):
        audit_log(AuditAction.REGISTER, request, details={"email": body.email}, status="failure")
        return JSONResponse(status_code=400, content={"error": "验证码错误或已过期"})

    ok, error = register_user(body.username, body.email, body.password)
    if not ok:
        audit_log(AuditAction.REGISTER, request, details={"email": body.email, "error": error}, status="failure")
        return JSONResponse(status_code=400, content={"error": error})

    token = create_token(body.username, body.email)
    audit_log(AuditAction.REGISTER, request, details={"username": body.username, "email": body.email}, status="success")
    return {"token": token, "username": body.username, "email": body.email}


@app.post("/api/v1/auth/login")
async def login(request: Request, body: LoginRequest):
    """登录（支持用户名或邮箱）"""
    from src.api.auth import authenticate_user, create_token

    ok, user_info = authenticate_user(body.login, body.password)
    if not ok:
        audit_log(AuditAction.LOGIN, request, details={"login": body.login}, status="failure")
        return JSONResponse(status_code=401, content={"error": "用户名/邮箱或密码错误"})

    token = create_token(user_info["username"], user_info["email"])
    audit_log(AuditAction.LOGIN, request, details={"username": user_info["username"], "email": user_info["email"]}, status="success")
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


# ---- 同步与文档管理 ----

@app.post("/api/v1/sync/webhook")
async def sync_webhook(request: Request):
    """接收 GitHub/GitLab webhook，自动同步 vault 并重建索引"""
    body = await request.body()

    # 验证 webhook signature
    if SYNC_WEBHOOK_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            SYNC_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return JSONResponse(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid webhook signature"},
            )

    # 执行同步
    sync_output = ""
    sync_error = ""
    try:
        if SYNC_SCRIPT_PATH and os.path.exists(SYNC_SCRIPT_PATH):
            result = subprocess.run(
                [SYNC_SCRIPT_PATH],
                capture_output=True,
                text=True,
                timeout=120,
            )
        elif os.path.exists(os.path.join(VAULT_PATH, ".git")):
            result = subprocess.run(
                ["git", "-C", VAULT_PATH, "pull"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        else:
            return JSONResponse(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                content={"error": "No sync method configured. Set SYNC_SCRIPT_PATH or ensure vault is a git repo."},
            )
        sync_output = result.stdout
        sync_error = result.stderr
        if result.returncode != 0:
            return JSONResponse(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Sync failed: {sync_error}", "stdout": sync_output},
            )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Sync timed out after 120s"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Sync error: {str(e)}"},
        )

    # 触发索引重建（多格式全量重建，确保所有格式都被索引）
    try:
        if pipeline is None:
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "Pipeline not initialized"},
            )
        stats = pipeline.rebuild_index_from_vault()
    except Exception as e:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": f"Rebuild failed: {str(e)}",
                "sync_output": sync_output,
            },
        )

    audit_log(
        AuditAction.SYNC,
        request,
        details={"source": "webhook", "rebuild_stats": stats},
        status="success",
    )
    return {
        "status": "ok",
        "sync_output": sync_output,
        "rebuild_stats": stats,
    }


@app.post("/api/v1/sync/trigger")
async def sync_trigger(request: Request, body: SyncTriggerRequest | None = None):
    """手动触发索引重建"""
    if pipeline is None:
        return JSONResponse(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Pipeline not initialized"},
        )

    incremental = body.incremental if body else True
    try:
        if incremental:
            stats = pipeline.build_index(incremental=True)
        else:
            stats = pipeline.rebuild_index_from_vault()
    except Exception as e:
        audit_log(AuditAction.SYNC, request, details={"incremental": incremental, "error": str(e)}, status="error")
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": str(e)},
        )

    audit_log(AuditAction.SYNC, request, details={"incremental": incremental, "rebuild_stats": stats}, status="success")
    return {"status": "ok", "rebuild_stats": stats}


@app.post("/api/v1/documents/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """上传单个文档到 vault 并触发索引重建"""
    from src.parsers.document_router import PARSER_MAP

    # 验证文件类型
    ext = Path(file.filename).suffix.lower()
    if ext not in PARSER_MAP:
        return JSONResponse(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            content={"error": f"Unsupported file type: {ext}. Supported: {list(PARSER_MAP.keys())}"},
        )

    # 安全处理文件名
    safe_name = Path(file.filename).name
    if safe_name.startswith(".") or "/" in safe_name or "\\" in safe_name:
        return JSONResponse(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid filename"},
        )

    # 保存文件
    vault_path = Path(VAULT_PATH)
    vault_path.mkdir(parents=True, exist_ok=True)
    file_path = vault_path / "uploads" / safe_name
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                content={"error": f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)"},
            )
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Failed to save file: {str(e)}"},
        )

    # 触发增量重建
    try:
        if pipeline is None:
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "Pipeline not initialized"},
            )
        stats = pipeline.rebuild_index_from_vault()
    except Exception as e:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Index rebuild failed: {str(e)}"},
        )

    audit_log(
        AuditAction.UPLOAD,
        request,
        details={"filename": safe_name, "size": len(content), "rebuild_stats": stats},
        status="success",
    )
    return {
        "status": "ok",
        "filename": safe_name,
        "saved_path": str(file_path.relative_to(vault_path)),
        "rebuild_stats": stats,
    }


@app.post("/api/v1/documents/batch-upload")
async def batch_upload_documents(request: Request, files: list[UploadFile] = File(...)):
    """批量上传文档到 vault 并触发索引重建"""
    from src.parsers.document_router import PARSER_MAP

    if len(files) > 20:
        return JSONResponse(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            content={"error": "Too many files (max 20)"},
        )

    vault_path = Path(VAULT_PATH)
    vault_path.mkdir(parents=True, exist_ok=True)
    upload_dir = vault_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    errors = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in PARSER_MAP:
            errors.append({"filename": file.filename, "error": f"Unsupported type: {ext}"})
            continue

        safe_name = Path(file.filename).name
        if safe_name.startswith(".") or "/" in safe_name or "\\" in safe_name:
            errors.append({"filename": file.filename, "error": "Invalid filename"})
            continue

        file_path = upload_dir / safe_name
        try:
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                errors.append({"filename": file.filename, "error": "File too large"})
                continue
            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append(safe_name)
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    # 触发重建
    try:
        if pipeline is None:
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "Pipeline not initialized"},
            )
        stats = pipeline.rebuild_index_from_vault()
    except Exception as e:
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Index rebuild failed: {str(e)}"},
        )

    audit_log(
        AuditAction.UPLOAD,
        request,
        details={"batch": True, "count": len(saved_files), "errors": len(errors), "rebuild_stats": stats},
        status="success" if not errors else "partial",
    )
    return {
        "status": "ok",
        "saved_files": saved_files,
        "errors": errors,
        "rebuild_stats": stats,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
