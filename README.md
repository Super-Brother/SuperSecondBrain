# SecondBrain Chat

基于 RAG 的知识库智能问答系统，支持 Obsidian 笔记、PDF、Word、PPT、Excel 等多种数据源。

> 从个人知识库到企业级知识库，一套代码渐进升级。

## 架构

```
用户提问 → Query脱敏 → Query改写 → 混合检索(BM25+向量) → 权限过滤 → Rerank重排
                                                    ↓
                                              元数据过滤(Milvus)
                                                    ↓
Prompt构建 → LLM生成 → 答案脱敏 → 答案+来源引用
    ↑
参考资料（按相关性排序）
```

### RAG 全链路三阶段

**① 离线索引链路（Indexing Pipeline）**
```
原始文档 → 文档解析 → 文本切片(Chunking) → 向量化(Embedding) → 存入向量数据库
```
| 环节 | 实现状态 | 说明 |
|------|----------|------|
| 文档解析 | ✅ | `DocumentRouter` 支持 `.md` `.pdf` `.docx` `.pptx` `.xlsx`，自动路由对应解析器 |
| 文本切片 | ✅ | 中文优化的 `RecursiveCharacterTextSplitter`，按二级标题→段落→句号→逗号优先级切分 |
| 向量化 | ✅ | `BAAI/bge-large-zh-v1.5` (1024d)，延迟加载 |
| 存储 | ✅ | FAISS（本地）/ Milvus（分布式），`VECTOR_STORE_BACKEND` 环境变量切换 |

**② 在线检索链路（Retrieval Pipeline）**
```
用户提问 → Query优化 → 混合检索(向量+关键词) → 重排序(Rerank) → TopK相关片段
```
| 环节 | 实现状态 | 说明 |
|------|----------|------|
| Query优化 | ✅ | LLM 查询改写（口语化→检索关键词），可开关；Query 脱敏（手机号/身份证/邮箱/银行卡） |
| 混合检索 | ✅ | 向量检索(0.7) + BM25关键词(0.3)，加权融合，支持 RRF；Milvus 支持元数据过滤 |
| 权限过滤 | ✅ | `SearchConfig` 按 `user_departments` / `user_access_level` 过滤 |
| 重排序 | ✅ | `BAAI/bge-reranker-base` CrossEncoder 精排 |

**③ 生成链路（Generation Pipeline）**
```
检索结果 + 用户问题 → Prompt构建 → LLM生成 → 答案返回（含引用来源）
```
| 环节 | 实现状态 | 说明 |
|------|----------|------|
| Prompt构建 | ✅ | SYSTEM_PROMPT + 上下文片段（按相关性排序）+ 历史对话（最近 20 轮，超过 20 条时自动摘要压缩，熔断保护） |
| LLM生成 | ✅ | OpenAI 兼容 API，支持同步 / SSE 流式；运行时可通过 `/api/v1/models/switch` 切换模型 |
| 答案返回 | ✅ | 答案脱敏 + Obsidian 双向链接自动转为可点击 URL + 来源引用卡片 |

### 缺失与待完善

| 能力 | 状态 | 优先级 |
|------|------|--------|
| 用户认证体系 | ⚠️ | 高 — Login/Register 端点已存在，但 `request.state.user` 始终为空，审计日志无法关联真实用户 |
| Metrics 持久化与告警 | ❌ | 高 — `MetricsCollector` 纯内存存储，重启丢失；缺少 Prometheus `/metrics` 导出端点和告警阈值配置 |
| 索引版本管理与灰度 | ❌ | 中 — 全量重建索引风险高，无版本号、无新旧索引切换机制、无回滚能力 |
| IM 集成（企微/飞书/钉钉） | ❌ | 中 — 仅 Web UI |
| 对象存储（MinIO/Ceph） | ❌ | 低 — 直接读取本地文件系统 |

## 核心特性

### 基础能力
- **多轮对话记忆** — 基于 SQLite 的会话管理，支持上下文追问；超过 20 轮自动调用 LLM 摘要压缩早期对话
- **流式输出** — SSE 流式返回，首 Token 延迟低，用户体验接近原生 ChatGPT
- **可点击来源引用** — 答案中 Obsidian 双向链接自动转为可点击 URL，附带来源引用卡片
- **增量索引** — 文件变更检测，只重建变更部分
- **Vault 自动同步** — watchdog 监听 Obsidian vault 目录，文件变更后自动触发增量索引重建
- **查询改写** — LLM 将口语化查询转为检索关键词
- **混合检索** — BM25 关键词匹配 + 向量语义检索，分数加权融合，支持 RRF
- **Rerank 重排序** — Cross-Encoder 精排，提升 Top-K 准确率
- **响应缓存双后端** — 内存 LRU 缓存默认启用；配置 `REDIS_URL` 后自动升级为 Redis 分布式缓存，Redis 故障时自动降级回内存缓存
- **限流熔断** — slowapi 限流（Redis 存储后端）+ `CircuitBreaker` 三态熔断器保护 LLM 调用，连续失败 5 次后自动熔断，60s 后半开探测
- **Token 追踪** — 统计 LLM 用量
- **日志审计** — RotatingFileHandler + JSON 结构化日志；SQLite 审计日志覆盖 chat/upload/sync/model_switch/login/register/feedback 8 类操作
- **API Key 认证** — 可选的安全认证

### 企业级能力
- **多格式文档支持** — Markdown / PDF / Word / PPT / Excel，自动路由解析
- **向量数据库可插拔** — FAISS（本地）/ Milvus（分布式），环境变量一键切换
- **权限隔离** — 部门 + 访问级别元数据过滤，检索时自动过滤无权文档
- **数据脱敏** — Query / 文档 / 答案 三级脱敏，支持手机号、身份证、邮箱、银行卡
- **自动化评估** — RAGAS 框架 + 启发式降级评估，持续监控 Faithfulness / Relevancy
- **可观测性** — `MetricsCollector` 内存指标（P50/P95/P99 延迟、Token 用量、成功率）通过 `/stats` 端点暴露；Prometheus + Grafana 可视化
- **容器化部署** — Docker Compose 编排 FastAPI + Redis + Prometheus + Grafana（轻量）；或 FastAPI + Milvus + vLLM + Prometheus + Grafana（企业级）

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 高性能异步 API |
| 前端 | Streamlit / Gradio / 内嵌 HTML | 多前端可选 |
| Embedding | BAAI/bge-large-zh-v1.5 | 1024 维，中文优化 |
| 向量数据库 | FAISS / Milvus | 本地 / 分布式可切换 |
| 关键词检索 | rank-bm25 + jieba | 中文分词 |
| Reranker | BAAI/bge-reranker-base | Cross-Encoder |
| LLM | OpenAI 兼容 API | 默认 Qwen2.5-3B，可升级至 72B |
| RAG 编排 | LangChain | Document / TextSplitter |
| 监控 | Prometheus + Grafana | 延迟 / 成功率 / Token |
| 评估 | RAGAS | 自动化评估 |

## 快速开始

### 1. 安装依赖

```bash
cd ~/projects/secondbrain-chat
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 配置你的 LLM 地址和向量数据库
```

### 3. 构建索引（首次运行）

```bash
# 从 Obsidian vault 构建
python scripts/build_index.py

# 增量更新
python scripts/build_index.py --incremental

# 从多格式文档目录构建（企业级）
python scripts/build_index.py --source-dir /path/to/docs --include-types .pdf .docx .md
```

### 4. 启动服务

```bash
# FastAPI API
uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# Streamlit 前端（推荐）
streamlit run scripts/streamlit_app.py

# Gradio 前端
python scripts/gradio_app.py
```

## 企业级配置

### 切换向量数据库（FAISS → Milvus）

```bash
# .env
VECTOR_STORE_BACKEND=milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_ENABLE_ACL=true
```

### 启用数据脱敏

```bash
# .env
SANITIZE_QUERY=true       # 用户问题发送 LLM 前脱敏
SANITIZE_DOCUMENT=false   # 文档入库前脱敏
SANITIZE_ANSWER=true      # 答案返回前脱敏
```

### 权限隔离（代码层）

```python
from src.retrievers.rag_retriever import SearchConfig

config = SearchConfig(
    user_departments=["技术部", "产品部"],
    user_access_level=3,
)
results = rag_retriever.retrieve(query, config)
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 知识库统计（含 Token 用量、P50/P95/P99 延迟） |
| POST | `/api/v1/sessions` | 创建会话 |
| GET | `/api/v1/sessions` | 列出会话 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| GET | `/api/v1/sessions/{id}/messages` | 获取会话历史消息 |
| POST | `/api/v1/chat` | 对话（非流式） |
| POST | `/api/v1/chat/stream` | 对话（SSE 流式） |
| GET | `/api/v1/domains` | 领域列表 |
| POST | `/api/v1/feedback` | 提交反馈 |
| GET | `/api/v1/models` | 列出可用模型 |
| POST | `/api/v1/models/switch` | 切换 LLM 模型（支持热切换） |
| POST | `/api/v1/auth/send-code` | 发送邮箱验证码 |
| POST | `/api/v1/auth/verify-code` | 验证邮箱验证码 |
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 用户登录 |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |
| POST | `/api/v1/sync/webhook` | Webhook 同步触发（支持 GitHub/GitLab） |
| POST | `/api/v1/sync/trigger` | 手动触发索引同步 |
| POST | `/api/v1/documents/upload` | 单文件上传 |
| POST | `/api/v1/documents/batch-upload` | 批量文件上传 |

## 项目结构

```
secondbrain-chat/
├── src/
│   ├── parsers/              # 解析器
│   │   ├── base_parser.py         # 抽象接口
│   │   ├── obsidian_parser.py     # Obsidian 解析
│   │   ├── markdown_parser.py     # 通用 Markdown
│   │   ├── pdf_parser.py          # PDF 解析
│   │   ├── office_parser.py       # Word / PPT / Excel
│   │   ├── document_router.py     # 文档路由（自动识别格式）
│   │   └── text_splitter.py       # 中文文本切分
│   ├── retrievers/           # 检索器
│   │   ├── rag_retriever.py       # 向量/BM25/混合/Rerank
│   │   ├── pipeline.py            # RAG Pipeline
│   │   ├── query_rewriter.py      # 查询改写
│   │   └── vector_store/          # 向量存储抽象层
│   │       ├── base.py            # 抽象基类
│   │       ├── faiss_store.py     # FAISS 实现
│   │       └── milvus_store.py    # Milvus 实现
│   ├── models/               # 模型
│   │   ├── llm_generator.py       # LLM 生成器
│   │   └── conversation.py        # 会话管理
│   ├── utils/                # 工具
│   │   ├── logger.py              # 日志（RotatingFileHandler + JSON 结构化）
│   │   ├── cache.py               # 内存响应缓存（LRU）
│   │   ├── redis_cache.py         # Redis 分布式缓存（自动降级回内存）
│   │   ├── circuit_breaker.py     # 三态熔断器（CLOSED/OPEN/HALF_OPEN）
│   │   ├── audit_logger.py        # 审计日志（SQLite 后端）
│   │   ├── metrics.py             # 监控指标（延迟分位数 / Token / 成功率）
│   │   ├── model_config_store.py  # 模型配置持久化（JSON）
│   │   ├── sanitizer.py           # 数据脱敏
│   │   └── vault_watcher.py       # Vault 文件监控（自动同步）
│   ├── evaluation/           # 评估
│   │   └── rag_evaluator.py       # RAGAS 评估器
│   └── api/                  # API
│       ├── app.py                 # FastAPI 应用
│       ├── auth.py                # 认证中间件
│       └── static.py              # 内嵌前端
├── scripts/
│   ├── build_index.py             # 索引构建
│   ├── streamlit_app.py           # Streamlit 前端
│   └── gradio_app.py              # Gradio 前端
├── tests/                    # 测试
├── data/index/               # 索引文件
├── Dockerfile
├── docker-compose.yml        # 轻量部署（推荐）
├── docker-compose.server.yml # 服务器部署（FAISS + Redis）
├── docker-compose.full.yml   # 企业级全栈部署（Milvus + vLLM）
├── deploy_server.sh          # 服务器一键部署脚本
├── DEPLOY.md                 # 服务器部署指南
├── prometheus.yml            # Prometheus 配置
└── requirements.txt
```

## Docker 部署

### 快速部署（推荐）

适用于生产服务器的轻量级部署，使用 FAISS + 外部 LLM API（DeepSeek/OpenAI）：

```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env，配置你的 LLM API 地址和密钥

# 2. 启动服务（API + Redis + Prometheus + Grafana）
docker-compose up -d

# 3. 查看状态
docker-compose ps
docker-compose logs -f api
```

**包含服务：**
| 服务 | 地址 | 说明 |
|------|------|------|
| API | `:8000` | FastAPI 主服务 |
| Redis | 内部 | 分布式缓存（可选，未配置 REDIS_URL 则使用内存缓存） |
| Prometheus | `:9090` | 指标采集 |
| Grafana | `:3000` | 可视化面板 |

**环境变量配置（`.env`）：**
```bash
# 必填：LLM 配置
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL=deepseek-chat

# 可选：Redis 缓存
# REDIS_URL=redis://redis:6379/0

# 可选：SMTP 邮件（用于注册验证码）
# SMTP_HOST=smtp.126.com
# SMTP_PORT=25
# SMTP_USER=yourname@126.com
# SMTP_PASSWORD=授权码
```

### 服务器部署（FAISS 版）

适用于无 GPU 的服务器，使用 FAISS + 外部 LLM API，国内镜像源优化：

```bash
# 一键部署（推荐）
./deploy_server.sh

# 或手动部署
docker compose -f docker-compose.server.yml up -d
```

**包含服务：**
| 服务 | 地址 | 说明 |
|------|------|------|
| API | `:8000` | FastAPI 主服务 |
| Redis | 内部 | 分布式缓存 |

**配置文件：** `.env.server`（参考 `.env.server.example`）

### 企业级完整部署

需要 GPU 服务器，包含 Milvus + vLLM 本地推理：

```bash
docker-compose -f docker-compose.full.yml up -d
```

**包含额外服务：**
| 服务 | 说明 |
|------|------|
| Milvus | 分布式向量数据库 |
| etcd | Milvus 元数据存储 |
| MinIO | 对象存储 |
| vLLM | 本地 LLM 推理（需 4x GPU） |

## 评估

```bash
# 运行自动化评估
source .venv/bin/activate
python -c "
from src.evaluation import RAGEvaluator
evaluator = RAGEvaluator()
result = evaluator.evaluate_single(
    query='什么是RAG',
    answer='RAG是检索增强生成技术',
    contexts=['RAG结合了信息检索和文本生成'],
)
print(result.metrics)
"
```

## 测试

```bash
pytest tests/ -v --cov=src
```

## License

MIT
