"""LLM 生成器

支持多种 LLM 后端：
- 本地 OpenAI 兼容 API（Qwen2.5 等）
- OpenAI API
- DeepSeek API
"""

import os
import time
from dataclasses import dataclass

from openai import OpenAI

from src.utils.circuit_breaker import get_circuit_breaker, CircuitBreakerOpen
from src.utils.logger import log


# 预设模型配置
PRESET_MODELS = {
    "ollama-local": {
        "name": "Ollama 本地 (Qwen2.5-3B)",
        "base_url": "http://localhost:11434/v1",
        "api_key": "not-needed",
        "model": "qwen2.5:3b",
    },
    "deepseek": {
        "name": "DeepSeek-V3",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
    "deepseek-reasoner": {
        "name": "DeepSeek-R1",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-reasoner",
    },
}


@dataclass
class LLMConfig:
    """LLM 配置"""

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout: float = 30.0
    stream_timeout: float = 60.0

    def __post_init__(self):
        # 从环境变量读取默认值
        self.base_url = self.base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = self.api_key or os.getenv("LLM_API_KEY", "not-needed")
        self.model = self.model or os.getenv("LLM_MODEL", "qwen2.5:3b")
        self.timeout = self.timeout or float(os.getenv("LLM_TIMEOUT", "30"))
        self.stream_timeout = self.stream_timeout or float(os.getenv("LLM_STREAM_TIMEOUT", "60"))


class LLMGenerator:
    """LLM 答案生成器"""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_count = 0
        # 主 LLM 熔断器实例
        self._breaker = get_circuit_breaker(name="llm")
        # 对话摘要熔断器（独立配置，更保守）
        self._summarizer_breaker = get_circuit_breaker(name="summarizer")

    def update_config(self, config: LLMConfig) -> None:
        """运行时切换模型配置"""
        self.config = config
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )

    @staticmethod
    def get_available_models() -> dict:
        """获取可用模型列表"""
        return {
            "presets": {
                key: {"name": val["name"], "model": val["model"], "base_url": val["base_url"]}
                for key, val in PRESET_MODELS.items()
            },
            "current": {
                "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
                "api_key": "***" if os.getenv("LLM_API_KEY") else "",
                "model": os.getenv("LLM_MODEL", "qwen2.5:3b"),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
            },
        }

    def _track_usage(self, response):
        if hasattr(response, "usage") and response.usage:
            self.total_prompt_tokens += response.usage.prompt_tokens or 0
            self.total_completion_tokens += response.usage.completion_tokens or 0
            self.call_count += 1

    def get_usage_stats(self) -> dict:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "call_count": self.call_count,
        }

    def summarize_conversation(self, history: list[dict]) -> str | None:
        """对多轮对话历史进行摘要压缩（带熔断保护）"""
        if not history or len(history) < 4:
            return None

        dialog = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}：{m['content'][:200]}"
            for m in history
        )

        def _call():
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个对话摘要助手。请将以下多轮对话压缩为一段简洁的摘要，保留关键信息和用户核心诉求。只输出摘要内容，不要添加解释。",
                    },
                    {"role": "user", "content": dialog},
                ],
                temperature=0.1,
                max_tokens=256,
                timeout=10.0,  # 摘要调用独立超时（更短）
            )
            self._track_usage(response)
            return response.choices[0].message.content.strip()

        try:
            return self._summarizer_breaker.call(_call)
        except CircuitBreakerOpen:
            log.warning("摘要熔断器已打开，跳过对话压缩")
            return None
        except Exception as e:
            log.warning("对话摘要失败: %s", e)
            return None

    def generate(
        self,
        query: str,
        context_docs: list,
        history: list[dict] | None = None,
    ) -> str:
        """基于检索结果生成答案，支持多轮对话历史（带熔断保护）"""
        messages = self._build_messages(query, context_docs, history)

        def _call():
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            self._track_usage(response)
            return response.choices[0].message.content

        try:
            return self._breaker.call(_call)
        except CircuitBreakerOpen:
            log.warning("LLM 熔断器打开，返回降级答案")
            return "（服务暂时不可用，请稍后重试。如果问题持续，请联系管理员。）"

    async def generate_stream(
        self,
        query: str,
        context_docs: list,
        history: list[dict] | None = None,
    ):
        """流式生成答案，支持多轮对话历史（带熔断保护和异常处理）"""
        if self._breaker.state.value == "open":
            log.warning("LLM 熔断器打开，流式请求被拒绝")
            yield "（服务暂时不可用，请稍后重试。）"
            return

        messages = self._build_messages(query, context_docs, history)

        try:
            stream = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            # 流式成功，记录成功
            self._breaker.record_success()
        except Exception as e:
            log.error("流式生成异常: %s", e)
            self._breaker.record_failure()
            yield f"\n\n[生成中断：{str(e)}]"

    def _build_messages(
        self,
        query: str,
        context_docs: list,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """构建完整的 messages 列表（含历史）"""
        context = self._build_context(context_docs)
        current_prompt = self._build_prompt(query, context)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": current_prompt})
        return messages

    def _build_context(self, docs: list) -> str:
        """构建检索结果上下文"""
        if not docs:
            return "（未检索到相关内容）"

        context_parts = []
        for i, doc in enumerate(docs):
            title = doc.metadata.get("title", "未知")
            source = doc.metadata.get("source_file", "")
            content = doc.page_content.strip()

            context_parts.append(
                f"【参考资料{i + 1}】标题：{title}\n"
                f"来源：{source}\n"
                f"内容：{content}"
            )

        return "\n\n---\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        """构建用户 Prompt"""
        return f"""参考以下资料回答用户的问题。如果资料中没有相关信息，请诚实地告知用户。

{context}

---

用户问题：{query}

请基于以上参考资料进行回答，并在回答中标注参考资料的编号。回答要简洁明了，重点突出。"""


SYSTEM_PROMPT = """你是一个智能知识库助手。你的职责是基于用户的个人笔记库回答问题。

核心原则：
1. 只基于提供的参考资料回答，不编造信息
2. 如果参考资料不足以回答问题，明确告知用户
3. 回答简洁清晰，引用具体来源
4. 对于编程类问题，可以给出代码示例
5. 对于观点类问题，保持客观中立的语气"""


if __name__ == "__main__":
    # 测试 LLM 连接
    from langchain_core.documents import Document

    config = LLMConfig()  # 从环境变量读取配置
    gen = LLMGenerator(config)

    # 模拟检索结果
    docs = [
        Document(
            page_content="LangChain 是一个用于开发由语言模型驱动的应用的框架。",
            metadata={"title": "LangChain介绍", "source_file": "test.md"},
        ),
        Document(
            page_content="RAG（检索增强生成）结合了信息检索和文本生成。",
            metadata={"title": "RAG介绍", "source_file": "test.md"},
        ),
    ]

    answer = gen.generate("什么是RAG？", docs)
    print(f"LLM 回答:\n{answer}")
