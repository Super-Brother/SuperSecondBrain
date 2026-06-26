"""SecondBrain Chat MCP Server。

通过 MCP 协议把知识库能力暴露给外部 Agent（Claude Desktop、Cursor 等）。
"""

from src.mcp.context import KBContext

__all__ = ["KBContext"]
