"""日志模块测试"""

import json
import logging
from pathlib import Path

import pytest

from src.utils.logger import setup_logger, JSONFormatter


class TestJSONFormatter:
    """JSON 格式器测试"""

    def test_basic_format(self):
        """基本 JSON 格式化"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="测试消息", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "测试消息"
        assert "timestamp" in parsed

    def test_request_id_in_output(self):
        """request_id 应包含在输出中"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="测试", args=(), exc_info=None,
        )
        record.request_id = "req-123"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["request_id"] == "req-123"

    def test_exception_in_output(self):
        """异常信息应包含在输出中"""
        import sys
        formatter = JSONFormatter()
        try:
            raise ValueError("测试异常")
        except:
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="出错了", args=(), exc_info=exc_info,
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "测试异常" in parsed["exception"]


class TestSetupLogger:
    """日志初始化测试"""

    def test_returns_logger(self, tmp_path, monkeypatch):
        """应返回 logging.Logger 实例"""
        monkeypatch.chdir(tmp_path)
        logger = setup_logger("test_logger_1")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger_1"

    def test_singleton_pattern(self, tmp_path, monkeypatch):
        """同一名字应返回同一实例"""
        monkeypatch.chdir(tmp_path)
        logger1 = setup_logger("test_singleton")
        logger2 = setup_logger("test_singleton")
        assert logger1 is logger2

    def test_log_level_from_env(self, tmp_path, monkeypatch):
        """LOG_LEVEL 环境变量应生效"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        logger = setup_logger("test_level")
        assert logger.level == logging.DEBUG

    def test_log_file_created(self, tmp_path, monkeypatch):
        """日志文件应被创建"""
        monkeypatch.chdir(tmp_path)
        logger = setup_logger("test_file")
        logger.info("测试写入文件")

        log_file = Path("data/logs/secondbrain.log")
        assert log_file.exists()
        content = log_file.read_text()
        assert "测试写入文件" in content

    def test_json_format_from_env(self, tmp_path, monkeypatch):
        """LOG_FORMAT=json 时应输出 JSON"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger("test_json")
        # 使用 StringIO 捕获输出
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logger.handlers[0].formatter)
        logger.handlers.clear()
        logger.addHandler(handler)

        logger.info("JSON 测试")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["message"] == "JSON 测试"
