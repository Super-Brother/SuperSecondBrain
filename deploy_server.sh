#!/bin/bash
# 服务器部署脚本（FAISS 版本）
# 用法: ./scripts/deploy_server.sh

set -e

echo "=== SecondBrain Chat 服务器部署 ==="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 请先安装 Docker"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ 请先安装 Docker Compose"
    exit 1
fi

# 检查配置文件
if [ ! -f .env.server ]; then
    echo "📝 创建 .env.server 配置文件..."
    cp .env.server.example .env.server
    echo "⚠️  请编辑 .env.server 配置 LLM 和文档路径"
    echo "   vim .env.server"
    exit 1
fi

# 禁用代理（解决 connection refused 问题）
echo "🔧 检查并禁用代理..."
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy
export DOCKER_BUILDKIT=0

# 检查 Docker 代理配置
if [ -f ~/.docker/config.json ]; then
    # 备份并清理代理配置
    cp ~/.docker/config.json ~/.docker/config.json.bak
    # 移除 proxy 配置（如果存在）
    if grep -q "proxies" ~/.docker/config.json; then
        echo "⚠️  检测到 Docker 代理配置，正在清理..."
        # 使用 python 清理 proxies 配置
        python3 -c "
import json
with open('$HOME/.docker/config.json', 'r') as f:
    config = json.load(f)
if 'proxies' in config:
    del config['proxies']
with open('$HOME/.docker/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('✅ 代理配置已清理')
"
    fi
fi

# 创建数据目录
mkdir -p data/index

# 构建并启动服务
echo "🚀 启动服务..."
docker compose -f docker-compose.server.yml up -d --build

# 等待 API 就绪
echo "⏳ 等待 API 就绪..."
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    sleep 5
    echo "   等待中..."
done
echo "✅ API 已就绪"

# 构建索引
echo "📊 构建索引（首次运行需要较长时间）..."
docker compose -f docker-compose.server.yml exec api python scripts/build_index.py

echo ""
echo "=== 部署完成 ==="
echo "API: http://$(hostname -I | awk '{print $1}'):8000"
echo "健康检查: http://$(hostname -I | awk '{print $1}'):8000/health"
