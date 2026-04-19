"""LLM 生成器

支持多种 LLM 后端：
- 本地 OpenAI 兼容 API（Qwen2.5 等）
- OpenAI API
- DeepSeek API
"""

import os
import json
from dataclasses import dataclass
from openai import OpenAI


@dataclass
class LLMConfig:
    """LLM 配置"""
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int = 1024

    def __post_init__(self):
        # 从环境变量读取默认值
        self.base_url = self.base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = self.api_key or os.getenv("LLM_API_KEY", "not-needed")
        self.model = self.model or os.getenv("LLM_MODEL", "qwen2.5:3b")


class LLMGenerator:
    """LLM 答案生成器"""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )

    def generate(self, query: str, context_docs: list) -> str:
        """基于检索结果生成答案"""
        context = self._build_context(context_docs)
        prompt = self._build_prompt(query, context)

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        return response.choices[0].message.content

    async def generate_stream(self, query: str, context_docs: list):
        """流式生成答案"""
        context = self._build_context(context_docs)
        prompt = self._build_prompt(query, context)

        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

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
                f"【参考资料{i+1}】标题：{title}\n"
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
