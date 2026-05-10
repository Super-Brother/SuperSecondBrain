"""查询改写器 — 将口语化查询转为检索友好的关键词"""

from openai import OpenAI

REWRITE_PROMPT = """你是一个查询改写助手。用户会输入一个自然语言问题，你需要将其改写为适合文档检索的关键词组合。

规则：
1. 提取核心概念和关键词
2. 去除口语化表达（"能告诉我"、"我想知道"、"怎么样"等）
3. 保留专业术语不拆分
4. 输出 1-2 句简练的检索查询
5. 只输出改写结果，不要解释

示例：
用户：怎么保持组织的创新能力？
改写：组织创新能力 保持方法 团队创新机制

用户：这个概念能再详细说说吗？
改写：上文讨论的核心概念 详细解释 定义 原理"""


class QueryRewriter:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def rewrite(self, query: str, timeout: float = 5.0) -> str:
        """将口语化查询改写为检索友好的关键词"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": REWRITE_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_tokens=128,
            timeout=timeout,
        )
        rewritten = response.choices[0].message.content.strip()
        # 如果改写失败或太长，回退到原始查询
        if not rewritten or len(rewritten) > len(query) * 3:
            return query
        return rewritten
