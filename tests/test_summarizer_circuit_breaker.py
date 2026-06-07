"""对话摘要熔断保护测试"""

import pytest
from unittest.mock import MagicMock, patch

from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    _breakers,
    _breakers_lock,
)
from src.models.llm_generator import LLMConfig, LLMGenerator


class TestSummarizeConversationCircuitBreaker:
    """对话摘要熔断保护测试"""

    def setup_method(self):
        """每个测试前清理 summarizer 熔断器"""
        with _breakers_lock:
            _breakers.pop("summarizer", None)
            _breakers.pop("test_summarizer", None)

    def test_summarizer_uses_independent_breaker(self):
        """summarize_conversation 应使用独立的 summarizer 熔断器"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        # 验证创建了 summarizer 熔断器
        assert gen._summarizer_breaker is not None
        assert gen._summarizer_breaker.name == "summarizer"
        # 验证与主 LLM 熔断器是不同实例
        assert gen._summarizer_breaker is not gen._breaker

    def test_summarizer_returns_none_on_circuit_open(self):
        """熔断器打开时，summarize_conversation 应返回 None"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        # 强制打开熔断器
        gen._summarizer_breaker._state = CircuitState.OPEN
        gen._summarizer_breaker._failure_count = 999
        gen._summarizer_breaker._last_failure_time = 0  # 远早于当前时间

        # 但 _can_attempt 检查会将其转移到 HALF_OPEN
        # 所以再强制为 OPEN 并设置较近的时间
        gen._summarizer_breaker._state = CircuitState.OPEN
        gen._summarizer_breaker._last_failure_time = __import__("time").time()

        result = gen.summarize_conversation([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
            {"role": "user", "content": "今天天气如何"},
            {"role": "assistant", "content": "今天天气不错。"},
        ])

        assert result is None

    def test_summarizer_records_failure_on_exception(self):
        """摘要调用异常时，应记录失败到 summarizer 熔断器"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        # Mock client 使其抛出异常
        gen.client = MagicMock()
        gen.client.chat.completions.create.side_effect = RuntimeError("API Error")

        result = gen.summarize_conversation([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
            {"role": "user", "content": "今天天气如何"},
            {"role": "assistant", "content": "今天天气不错。"},
        ])

        assert result is None
        assert gen._summarizer_breaker._failure_count > 0

    def test_summarizer_records_success(self):
        """摘要调用成功时，应记录成功"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        # Mock 响应
        mock_response = MagicMock()
        mock_response.usage = None
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  摘要内容  "

        gen.client = MagicMock()
        gen.client.chat.completions.create.return_value = mock_response

        # 先记录一次失败，再成功
        gen._summarizer_breaker.record_failure()
        assert gen._summarizer_breaker._failure_count == 1

        result = gen.summarize_conversation([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
            {"role": "user", "content": "今天天气如何"},
            {"role": "assistant", "content": "今天天气不错。"},
        ])

        assert result == "摘要内容"
        # 成功后失败计数重置
        assert gen._summarizer_breaker._failure_count == 0

    def test_summarizer_short_timeout(self):
        """摘要调用应使用较短超时"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        gen.client = MagicMock()
        mock_response = MagicMock()
        mock_response.usage = None
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "摘要"
        gen.client.chat.completions.create.return_value = mock_response

        gen.summarize_conversation([
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"},
            {"role": "assistant", "content": "回答2"},
        ])

        # 验证调用时使用了 timeout=10.0
        call_kwargs = gen.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["timeout"] == 10.0

    def test_short_history_skips_summary(self):
        """历史消息少于 4 条时，应跳过摘要"""
        config = LLMConfig(base_url="http://test", api_key="test", model="test")
        gen = LLMGenerator(config)

        result = gen.summarize_conversation([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ])

        assert result is None
