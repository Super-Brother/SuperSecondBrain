import asyncio
from types import SimpleNamespace

from langchain_core.documents import Document
from starlette.requests import Request

from src.retrievers.pipeline import PipelineConfig, SecondBrainPipeline, get_direct_reply
from src.retrievers.query_rewriter import QueryRewriter


class _FakeCompletions:
    def __init__(self, content: str):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_query_rewriter_includes_recent_history_context():
    completions = _FakeCompletions("混合检索 权重配置")
    rewriter = QueryRewriter("http://example.test/v1", "test-key", "test-model")
    rewriter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    result = rewriter.rewrite(
        "这个权重怎么调？",
        history=[
            {"role": "user", "content": "RAG 里面 BM25 和向量检索怎么融合？"},
            {"role": "assistant", "content": "可以用混合检索权重融合。"},
        ],
    )

    assert result == "混合检索 权重配置"
    messages = completions.kwargs["messages"]
    assert messages[-1] == {"role": "user", "content": "这个权重怎么调？"}
    assert any(
        message["role"] == "system"
        and "最近对话上下文" in message["content"]
        and "混合检索" in message["content"]
        for message in messages
    )


def test_pipeline_sanitizes_query_and_history_before_rewrite(monkeypatch):
    monkeypatch.setenv("SANITIZE_QUERY", "true")

    class FakeRewriter:
        def __init__(self):
            self.query = None
            self.history = None

        def rewrite(self, query, history=None):
            self.query = query
            self.history = history
            return "脱敏后检索词"

    pipeline = SecondBrainPipeline(PipelineConfig(enable_query_rewrite=True))
    pipeline.query_rewriter = FakeRewriter()

    rewritten, original = pipeline._rewrite_query(
        "帮我查一下 13800138000 的资料",
        history=[{"role": "user", "content": "我的邮箱是 zhangsan@example.com"}],
    )

    assert rewritten == "脱敏后检索词"
    assert original == "帮我查一下 13800138000 的资料"
    assert pipeline.query_rewriter.query == "帮我查一下 138****8000 的资料"
    assert pipeline.query_rewriter.history == [
        {"role": "user", "content": "我的邮箱是 zh***@example.com"}
    ]


def test_chat_rewrites_search_with_history_but_generates_from_original_query(monkeypatch):
    class FakeRewriter:
        def __init__(self):
            self.history = None

        def rewrite(self, query, history=None):
            self.history = history
            return "混合检索 权重配置"

    class FakeRetriever:
        def __init__(self):
            self.query = None

        def retrieve(self, query, config):
            self.query = query
            return [
                (
                    Document(
                        page_content="BM25 与向量检索可通过权重融合。",
                        metadata={"title": "Hybrid", "source_file": "hybrid.md"},
                    ),
                    0.91,
                )
            ]

    class FakeGenerator:
        def __init__(self):
            self.query = None
            self.history = None

        def generate(self, query, docs, history=None):
            self.query = query
            self.history = history
            return "回答"

    pipeline = SecondBrainPipeline(PipelineConfig(enable_query_rewrite=True))
    pipeline.query_rewriter = FakeRewriter()
    pipeline.rag_retriever = FakeRetriever()
    pipeline.llm_generator = FakeGenerator()
    monkeypatch.setattr(pipeline, "_ensure_llm", lambda: None)

    history = [{"role": "user", "content": "怎么做混合检索？"}]
    result = pipeline.chat("这个权重怎么调？", history=history)

    assert result["answer"] == "回答"
    assert pipeline.query_rewriter.history == history
    assert pipeline.rag_retriever.query == "混合检索 权重配置"
    assert pipeline.llm_generator.query == "这个权重怎么调？"
    assert pipeline.llm_generator.history == history


def test_chat_replies_to_greeting_without_retrieval(monkeypatch):
    class FailingRetriever:
        def retrieve(self, query, config):
            raise AssertionError("greeting should not enter retrieval")

    pipeline = SecondBrainPipeline(PipelineConfig(enable_query_rewrite=True))
    pipeline.rag_retriever = FailingRetriever()
    monkeypatch.setattr(pipeline, "_ensure_llm", lambda: None)

    result = pipeline.chat("哈喽")

    assert result["sources"] == []
    assert result["query"] == "哈喽"
    assert "你好" in result["answer"]
    assert "知识库" in result["answer"]


def test_direct_reply_conservatively_expands_short_chinese_greetings():
    for query in ["哈喽呀", "你好啊", "早上好", "在吗？"]:
        assert get_direct_reply(query) is not None

    assert get_direct_reply("你好 RAG 是什么") is None
    assert get_direct_reply("hello there") is None


def test_api_pipeline_config_reads_query_rewrite_env(monkeypatch, tmp_path):
    from src.api import app as api_app

    monkeypatch.setenv("ENABLE_QUERY_REWRITE", "true")
    monkeypatch.setattr(api_app, "is_desktop_mode", lambda: False)
    monkeypatch.setattr(
        api_app,
        "ensure_app_dirs",
        lambda: SimpleNamespace(index_dir=tmp_path / "index"),
    )
    monkeypatch.setattr(api_app, "load_model_config", lambda: None)
    monkeypatch.setattr(api_app, "_load_pipeline_types", lambda: None)
    monkeypatch.setattr(api_app, "PipelineConfig", PipelineConfig)

    config = api_app._resolve_pipeline_config()

    assert config.enable_query_rewrite is True


def test_api_chat_replies_to_greeting_without_loaded_index(monkeypatch):
    from src.api import app as api_app

    monkeypatch.setattr(api_app, "pipeline", None)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": [],
            "client": ("testclient", 50000),
        }
    )

    response = asyncio.run(
        api_app.chat(
            request,
            api_app.ChatRequest(query="hello", session_id="greeting-session"),
        )
    )

    assert response.session_id == "greeting-session"
    assert response.sources == []
    assert "你好" in response.answer
    assert "索引未加载" not in response.answer
