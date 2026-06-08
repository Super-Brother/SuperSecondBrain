#!/bin/bash
# 清理占用 8000 端口的进程

PIDS=$(lsof -ti:8000 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "Killing processes on port 8000: $PIDS"
    echo "$PIDS" | xargs kill -9 2>/dev/null
    echo "Port 8000 cleaned"
else
    echo "Port 8000 is already free"
fi
