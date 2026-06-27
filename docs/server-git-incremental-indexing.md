# 服务器 Git 增量索引部署指南

本指南面向**个人服务器**场景，说明如何通过 Git 定时拉取 vault 变更并触发 FAISS 增量索引重建。

**范围说明**：本指南继续使用 FAISS 单机方案，不引入 Milvus。Milvus 是未来规模化（多实例、ACL、元数据过滤）的可选升级路径，不是当前个人服务器推荐方案。

## 目录布局

推荐在个人服务器上使用以下目录结构：

```text
/home/<user>/secondbrain/
├── app/                    # 应用代码仓库
│   ├── scripts/sync_vault_incremental.py
│   ├── src/
│   └── ...
├── data/
│   ├── vault/              # Git 知识库目录（VAULT_PATH）
│   └── index/              # FAISS 索引目录（INDEX_DIR）
└── logs/
    └── sync.log            # 同步脚本日志（可选）
```

## 环境变量

在 `~/.bashrc`、systemd service 或 `.env` 中配置：

```bash
# 应用路径
VAULT_PATH=/home/<user>/secondbrain/data/vault
INDEX_DIR=/home/<user>/secondbrain/data/index

# 同步方式二选一：
# 1. vault 目录本身是 Git 仓库，脚本会直接 git pull
# 2. 配置自定义同步脚本，例如通过 syncthing、rsync 等更新 vault
SYNC_SCRIPT_PATH=/home/<user>/secondbrain/scripts/sync_vault.sh

# LLM 与 Embedding（与 .env.example 一致）
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32

# 其他可选配置
# REDIS_URL=redis://localhost:6379/0
# API_KEY=your-secret-api-key
```

如果使用 `SYNC_SCRIPT_PATH`，脚本需要自行完成 vault 目录的更新（如 `git pull`、`rsync` 等），并返回 exit code 0 表示成功。

## 首次全量构建

首次部署时需要构建全量索引：

```bash
cd /home/<user>/secondbrain/app
source .venv/bin/activate
# 或使用 conda：conda activate secondbrain-chat

# 方式 1：从 Obsidian vault 构建（仅 Markdown）
python scripts/build_index.py

# 方式 2：从多格式文档目录构建（推荐服务器多格式场景）
python scripts/build_index.py \
  --source-dir /home/<user>/secondbrain/data/vault \
  --include-types .md,.pdf,.docx,.pptx,.xlsx
```

构建完成后确认索引文件存在：

```bash
ls "$INDEX_DIR"
# faiss.index  documents.pkl  bm25.pkl  manifest.json  stats.json
```

## 配置 systemd Timer

创建 `/etc/systemd/system/secondbrain-sync.service`：

```ini
[Unit]
Description=SecondBrain Chat vault sync and incremental index rebuild
After=network.target

[Service]
Type=oneshot
User=<user>
Group=<user>
WorkingDirectory=/home/<user>/secondbrain/app
Environment="VAULT_PATH=/home/<user>/secondbrain/data/vault"
Environment="INDEX_DIR=/home/<user>/secondbrain/data/index"
# 如果使用自定义同步脚本，取消下一行注释
# Environment="SYNC_SCRIPT_PATH=/home/<user>/secondbrain/scripts/sync_vault.sh"
Environment="LLM_BASE_URL=https://api.deepseek.com/v1"
Environment="LLM_API_KEY=sk-xxxxxxxx"
Environment="LLM_MODEL=deepseek-chat"
Environment="EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5"
Environment="EMBEDDING_DEVICE=cpu"
Environment="EMBEDDING_BATCH_SIZE=32"
Environment="TOKENIZERS_PARALLELISM=false"
Environment="OMP_NUM_THREADS=4"
Environment="SPLIT_STRATEGY=legacy"
ExecStart=/home/<user>/secondbrain/app/.venv/bin/python scripts/sync_vault_incremental.py
# 或：
# ExecStart=/home/<user>/anaconda3/envs/secondbrain-chat/bin/python scripts/sync_vault_incremental.py
StandardOutput=append:/home/<user>/secondbrain/logs/sync.log
StandardError=append:/home/<user>/secondbrain/logs/sync.log
```

创建 `/etc/systemd/system/secondbrain-sync.timer`：

```ini
[Unit]
Description=Run SecondBrain Chat vault sync every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
```

启用并启动 timer：

```bash
sudo systemctl daemon-reload
sudo systemctl enable secondbrain-sync.timer
sudo systemctl start secondbrain-sync.timer

# 查看状态
sudo systemctl status secondbrain-sync.timer
sudo systemctl list-timers secondbrain-sync.timer
```

默认 10 分钟一次，可根据 vault 更新频率调整 `OnUnitActiveSec`。

## 手动运行与查看日志

手动执行一次同步：

```bash
cd /home/<user>/secondbrain/app
python scripts/sync_vault_incremental.py
```

输出示例：

```json
{
  "status": "success",
  "old_head": "abc1234",
  "new_head": "def5678",
  "changed_files": ["笔记/RAG.md"],
  "deleted_files": [],
  "stats": {
    "total_notes": 120,
    "total_chunks": 350
  },
  "duration_seconds": 12.34,
  "message": ""
}
```

查看 timer 日志：

```bash
sudo journalctl -u secondbrain-sync.service -f

# 或查看文件日志
tail -f /home/<user>/secondbrain/logs/sync.log
```

## 失败恢复

### 场景 1：同步脚本返回 locked

表示上一次同步尚未完成。可能原因：

- 上一次同步因网络或模型加载过慢仍在运行
- 上一次同步异常退出后未释放锁文件

处理：

```bash
# 检查是否有 Python 进程在运行
ps aux | grep sync_vault_incremental

# 如果没有进程，手动删除锁文件
rm "$INDEX_DIR/.sync.lock"
```

### 场景 2：Git 拉取冲突或非 fast-forward

```bash
cd "$VAULT_PATH"
git status

# 手动解决冲突或分叉后再拉取
git pull --rebase
```

### 场景 3：索引损坏

如果索引文件损坏导致加载失败，可删除后重新全量构建：

```bash
# 备份旧索引（可选）
mv "$INDEX_DIR" "$INDEX_DIR.bak.$(date +%Y%m%d%H%M%S)"
mkdir -p "$INDEX_DIR"

# 重新全量构建
python scripts/build_index.py --source-dir "$VAULT_PATH"
```

### 场景 4：LLM 或 Embedding 调用失败

检查环境变量和服务可达性：

```bash
curl "$LLM_BASE_URL/models" -H "Authorization: Bearer $LLM_API_KEY"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL')"
```

## 与 Webhook/手动触发对比

| 触发方式 | 适用场景 | 说明 |
|---|---|---|
| systemd timer | 个人服务器定时同步 | 本指南方案，稳定、可回查日志 |
| `/api/v1/sync/webhook` | 有公网 IP 接收 GitHub/GitLab webhook | 需要配置 `SYNC_WEBHOOK_SECRET` |
| `/api/v1/sync/trigger` | 手动触发 | 适合调试或临时同步 |
| `scripts/sync_vault_incremental.py` | 被 timer/cron 调用 | 包含锁、HEAD 检测、JSON 摘要 |

三种触发方式最终都调用 `SecondBrainPipeline.rebuild_index_from_vault(incremental=True)`，索引语义一致。

## 为什么不使用 Milvus？

当前个人服务器场景下：

- FAISS 单机性能足够（数万到数十万文档）
- FAISS 无需额外服务进程，部署和备份简单
- 本方案已通过文件锁和原子写入保证索引一致性

当未来需要以下能力时再考虑 Milvus：

- 多实例共享索引
- 细粒度 ACL 权限过滤
- 千万级以上向量规模
- 分布式高可用

切换方式：设置 `VECTOR_STORE_BACKEND=milvus` 并参考 `docker-compose.full.yml`。
