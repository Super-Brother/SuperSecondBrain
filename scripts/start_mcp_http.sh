#!/bin/bash
# 启动 secondbrain MCP HTTP/SSE server
# 用法：bash scripts/start_mcp_http.sh

source /Users/zhangwenchao/anaconda3/etc/profile.d/conda.sh
conda activate secondbrain-chat
exec python /Users/zhangwenchao/projects/secondbrain-chat/src/mcp/server.py --transport sse --port 8080
