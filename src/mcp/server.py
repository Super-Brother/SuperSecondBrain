"""SecondBrain Chat MCP Server 启动入口。

提供两种运行方式：
1. stdio（默认）：供 Claude Desktop、Cursor 等本地 MCP Client 使用
2. SSE：供远程 HTTP Client 使用，可嵌入 FastAPI lifespan

示例（Claude Desktop 配置）：
{
  "mcpServers": {
    "secondbrain": {
      "command": "python",
      "args": ["/path/to/src/mcp/server.py"]
    }
  }
}
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 把项目根目录加入路径，确保能 import src
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 提前加载 .env，避免为了读取 VAULT_PATH 而导入 app.py（app.py 会拉入大量模块）
from dotenv import load_dotenv

load_dotenv()

from src.utils.logger import log


def _configure_logging_for_stdio():
    """MCP stdio 模式下，日志必须写到 stderr，不能占用 stdout。"""
    logger = logging.getLogger("secondbrain")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            logger.removeHandler(handler)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)

    # 其他可能污染 stdout 的 root handler 也清理掉
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            root.removeHandler(handler)


# 在导入任何可能写日志的模块前，先确保 stdout 不被日志占用
_configure_logging_for_stdio()

from fastmcp import FastMCP

from src.mcp.context import KBContext
from src.mcp.tools import register_tools


def _resolve_pipeline():
    """延迟导入并返回 pipeline，避免循环导入。"""
    from src.api.app import ensure_pipeline
    return ensure_pipeline()


def _resolve_vault_path():
    """返回 VAULT_PATH，优先从环境变量读取，避免导入 app.py 增加启动时间。"""
    vault_path = os.getenv("VAULT_PATH")
    if vault_path:
        return vault_path
    # fallback：从 app.py 读取（兼容桌面端等动态设置）
    from src.api.app import VAULT_PATH
    return VAULT_PATH


def create_mcp_server(pipeline=None, conv_manager=None, vault_path: str | None = None) -> FastMCP:
    """创建并配置 FastMCP Server。

    默认不立即加载 pipeline，避免 MCP server 启动时间过长导致 Client 超时。
    Pipeline 会在第一次 tool 调用时懒加载。

    Args:
        pipeline: SecondBrainPipeline 实例；为 None 时首次调用懒加载
        conv_manager: ConversationManager 实例
        vault_path: vault 根目录路径；为 None 时从环境变量/配置推导
    """
    if vault_path is None:
        vault_path = _resolve_vault_path()

    ctx = KBContext(pipeline=pipeline, vault_path=vault_path, conv_manager=conv_manager)
    mcp = FastMCP("secondbrain-kb")
    register_tools(mcp, ctx)
    log.info("MCP Server 已创建并注册知识库 tools（pipeline 懒加载）")
    return mcp


def main():
    parser = argparse.ArgumentParser(description="SecondBrain MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport 类型（默认 stdio）",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "127.0.0.1"),
        help="SSE 模式监听地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8080")),
        help="SSE 模式监听端口",
    )
    args = parser.parse_args()

    mcp = create_mcp_server()

    if args.transport == "stdio":
        # 禁用 FastMCP banner，避免任何可能的 stdout 污染
        os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")
        mcp.run(show_banner=False)
    else:
        # SSE 模式：启动独立服务器（兼容性最好的 HTTP 模式）
        mcp.run(transport="sse", host=args.host, port=args.port, show_banner=False)


if __name__ == "__main__":
    main()
