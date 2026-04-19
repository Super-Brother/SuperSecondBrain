"""FastAPI 应用入口"""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig
from src.api.static import HTML_TEMPLATE


# ---- 配置 ----

VAULT_PATH = os.getenv(
    "VAULT_PATH",
    "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
)
INDEX_DIR = os.getenv("INDEX_DIR", "data/index")


# ---- 全局 pipeline ----

pipeline: SecondBrainPipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载索引"""
    global pipeline
    config = PipelineConfig(
        vault_path=VAULT_PATH,
        index_dir=INDEX_DIR,
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", "not-needed"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:3b"),
    )
    pipeline = SecondBrainPipeline(config)

    index_path = Path(INDEX_DIR)
    if (index_path / "faiss.index").exists():
        print(f"[Startup] 加载已有索引: {INDEX_DIR}")
        pipeline.load_index(INDEX_DIR)
    else:
        print(f"[Startup] 未找到索引，需要先构建。请运行: python scripts/build_index.py")
        # 不阻塞启动，但对话会返回错误

    yield


# ---- FastAPI App ----

app = FastAPI(
    title="SecondBrain Chat API",
    description="基于 RAG 的个人知识库智能问答系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 数据模型 ----

class ChatRequest(BaseModel):
    query: str
    domain: str | None = None
    top_k: int | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    query: str
    answer: str
    sources: list[dict]


# ---- API 端点 ----

@app.get("/health")
async def health_check():
    """健康检查"""
    if pipeline is None:
        return {"status": "starting", "index_loaded": False}
    return {
        "status": "ok",
        "index_loaded": pipeline.rag_retriever is not None,
        "stats": pipeline.get_stats(),
    }


@app.get("/stats")
async def get_stats():
    """知识库统计"""
    if pipeline is None:
        return {"error": "服务未就绪"}
    return pipeline.get_stats()


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """对话接口（非流式）"""
    if pipeline is None or pipeline.rag_retriever is None:
        return ChatResponse(
            query=request.query,
            answer="知识库索引未加载，请先构建索引。",
            sources=[],
        )

    result = pipeline.chat(
        query=request.query,
        domain=request.domain,
        top_k=request.top_k,
    )
    return ChatResponse(**result)


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """对话接口（流式 SSE）"""
    if pipeline is None or pipeline.rag_retriever is None:
        async def error_stream():
            yield "data: " + json.dumps({"error": "知识库索引未加载"}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def generate():
        # 先发送来源
        sources_sent = False
        async for chunk in pipeline.chat_stream(
            query=request.query,
            domain=request.domain,
            top_k=request.top_k,
        ):
            if chunk.startswith("__SOURCES__:"):
                # 来源信息作为第一个事件
                sources_json = chunk.replace("__SOURCES__:", "").strip()
                yield f"data: {json.dumps({'type': 'sources', 'data': json.loads(sources_json)}, ensure_ascii=False)}\n\n"
                sources_sent = True
            else:
                yield f"data: {json.dumps({'type': 'answer', 'content': chunk}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/domains")
async def list_domains():
    """列出所有领域"""
    if pipeline is None:
        return {"error": "服务未就绪"}
    stats = pipeline.get_stats()
    return {"domains": stats.get("domain_distribution", {})}


@app.get("/", response_class=HTMLResponse)
async def index():
    """前端页面"""
    return HTML_TEMPLATE


# ---- 启动命令 ----
# uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
