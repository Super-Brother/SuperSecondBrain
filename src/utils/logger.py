"""统一日志配置

支持：
- stdout 输出（默认）
- 文件输出（RotatingFileHandler，自动旋转）
- JSON 结构化格式（通过环境变量切换）
- 日志级别通过环境变量配置

Usage:
    from src.utils.logger import log
    log.info("消息")
"""

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """JSON 结构化日志格式器"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logger(name: str = "secondbrain") -> logging.Logger:
    """初始化日志器

    环境变量：
        LOG_LEVEL: 日志级别（DEBUG/INFO/WARNING/ERROR，默认 INFO）
        LOG_FORMAT: 格式（text/json，默认 text）
        LOG_MAX_BYTES: 单个日志文件最大字节数（默认 10MB）
        LOG_BACKUP_COUNT: 保留备份数量（默认 5）
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # 日志级别
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)

    # 格式选择
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # stdout Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # 文件 Handler（RotatingFileHandler）
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 默认 10MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    file_handler = RotatingFileHandler(
        filename=log_dir / "secondbrain.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


log = setup_logger()
