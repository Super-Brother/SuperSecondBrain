"""MCP 配置端点集成测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_mcp_config_endpoint():
    """ /mcp/config 返回可复制的 Claude Desktop stdio 配置。 """
    from src.api.app import app

    with TestClient(app) as client:
        r = client.get("/mcp/config")
        assert r.status_code == 200
        cfg = r.json()
        assert "mcpServers" in cfg
        assert "secondbrain" in cfg["mcpServers"]
        sb = cfg["mcpServers"]["secondbrain"]
        assert "command" in sb
        assert "args" in sb
        assert sb["command"] == "python"
        assert sb["args"][0].endswith("src/mcp/server.py")
