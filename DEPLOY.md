# 服务器部署指南

## 快速部署

```bash
# 1. 克隆代码
git clone <your-repo-url> secondbrain-chat
cd secondbrain-chat

# 2. 配置环境变量
cp .env.server .env.server
vim .env.server  # 修改 LLM 配置和文档路径

# 3. 上传文档（如果需要）
# 将 Obsidian vault 或文档目录上传到服务器
rsync -avz /path/to/docs user@server:/data/docs

# 4. 运行部署脚本
./scripts/deploy_server.sh
```

## 手动部署

### 1. 配置环境变量

```bash
cp .env.server .env.server
```

编辑 `.env.server`：
- `LLM_BASE_URL`: LLM 服务地址（如 Ollama、vLLM）
- `DOCS_PATH`: 文档目录路径

### 2. 启动服务

```bash
docker compose -f docker-compose.server.yml up -d
```

### 3. 构建索引

```bash
# 首次全量构建（耗时较长）
docker compose -f docker-compose.server.yml exec api python scripts/build_index.py

# 后续增量更新
docker compose -f docker-compose.server.yml exec api python scripts/build_index.py --incremental
```

### 4. 验证服务

```bash
# 检查健康状态
curl http://localhost:8000/health

# 测试聊天
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "你好"}'
```

## 索引同步

### 从服务器下载索引到本地

```bash
rsync -avz user@server:/path/to/secondbrain-chat/data/index/ ./data/index/
```

### 从本地上传索引到服务器

```bash
rsync -avz ./data/index/ user@server:/path/to/secondbrain-chat/data/index/
```

## 更新部署

```bash
# 拉取最新代码
git pull

# 重启服务
docker compose -f docker-compose.server.yml up -d --build

# 增量更新索引
docker compose -f docker-compose.server.yml exec api python scripts/build_index.py --incremental
```

## 常用命令

```bash
# 查看日志
docker compose -f docker-compose.server.yml logs -f api

# 停止服务
docker compose -f docker-compose.server.yml down

# 重启单个服务
docker compose -f docker-compose.server.yml restart api

# 进入容器
docker compose -f docker-compose.server.yml exec api bash
```

## 服务器配置建议

| 资源 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2核 | 4核+ |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 20GB | 50GB+ |
| 网络 | 1Mbps | 10Mbps+ |

## 故障排查

### 索引构建慢

```bash
# 检查资源使用
docker stats

# 解决方案：
# 1. 增加服务器配置
# 2. 使用增量构建
# 3. 本地构建后同步到服务器
```

### LLM 连接失败

```bash
# 检查 LLM 服务
curl http://localhost:11434/api/tags

# 检查网络连通性
docker compose -f docker-compose.server.yml exec api curl http://host.docker.internal:11434/api/tags
```
