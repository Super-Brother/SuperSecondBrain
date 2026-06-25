#!/usr/bin/env python
"""Run the Feishu bot through WebSocket long connection."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.api import app as app_module
from src.integrations.feishu import FeishuAPIClient, FeishuConfig
from src.integrations.feishu_ws import FeishuWsWorker
from src.utils.audit_logger import AuditAction, audit_log
from src.utils.logger import log


def _record_audit(details: dict, status: str) -> None:
    audit_log(
        AuditAction.CHAT,
        None,
        details={"source": "feishu_ws", **details},
        status=status,
    )


def build_worker() -> FeishuWsWorker:
    config = FeishuConfig.from_env()
    client = FeishuAPIClient(config)
    return FeishuWsWorker(
        config=config,
        client=client,
        ask_knowledge=app_module._ask_knowledge_for_feishu,
        audit_recorder=_record_audit,
        processed_message_ids=app_module.feishu_processed_message_ids,
        log_level=os.getenv("FEISHU_LOG_LEVEL", "INFO").upper(),
    )


def main() -> None:
    load_dotenv()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    lifespan = app_module.lifespan(app_module.app)
    try:
        loop.run_until_complete(lifespan.__aenter__())
        log.info("SecondBrain Chat 已初始化，准备启动飞书长连接")
        build_worker().start()
    finally:
        loop.run_until_complete(lifespan.__aexit__(None, None, None))
        loop.close()
        asyncio.set_event_loop(None)


if __name__ == "__main__":
    main()
