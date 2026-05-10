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

## 核心特性

### 基础能力
- **多轮对话记忆** — 基于 SQLite 的会话管理，支持上下文追问
- **增量索引** — 文件变更检测，只重建变更部分
- **查询改写** — LLM 将口语化查询转为检索关键词
- **混合检索** — BM25 关键词匹配 + 向量语义检索，分数加权融合
- **Rerank 重排序** — Cross-Encoder 精排，提升 Top-K 准确率
- **响应缓存** — LRU 缓存重复查询，毫秒级响应
- **Token 追踪** — 统计 LLM 用量
- **API Key 认证** — 可选的安全认证

### 企业级能力
- **多格式文档支持** — Markdown / PDF / Word / PPT / Excel，自动路由解析
- **向量数据库可插拔** — FAISS（本地）/ Milvus（分布式），环境变量一键切换
- **权限隔离** — 部门 + 访问级别元数据过滤，检索时自动过滤无权文档
- **数据脱敏** — Query / 文档 / 答案 三级脱敏，支持手机号、身份证、邮箱、银行卡
- **自动化评估** — RAGAS 框架 + 启发式降级评估，持续监控 Faithfulness / Relevancy
- **可观测性** — Prometheus + Grafana 监控延迟、成功率、Token 使用量
- **容器化部署** — Docker Compose 编排 FastAPI + Milvus + vLLM + Prometheus + Grafana

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 高性能异步 API |
| 前端 | Streamlit / Gradio / 内嵌 HTML | 多前端可选 |
| Embedding | BAAI/bge-large-zh-v1.5 | 768 维，中文优化 |
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
| GET | `/stats` | 知识库统计（含 Token 用量） |
| POST | `/api/v1/sessions` | 创建会话 |
| GET | `/api/v1/sessions` | 列出会话 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| POST | `/api/v1/chat` | 对话（非流式） |
| POST | `/api/v1/chat/stream` | 对话（SSE 流式） |
| GET | `/api/v1/domains` | 领域列表 |
| POST | `/api/v1/feedback` | 提交反馈 |

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
│   │   ├── logger.py              # 日志
│   │   ├── cache.py               # 响应缓存
│   │   ├── sanitizer.py           # 数据脱敏
│   │   └── metrics.py             # 监控指标
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
├── docker-compose.yml        # 企业级全栈部署
├── prometheus.yml            # Prometheus 配置
└── requirements.txt
```

## Docker 部署

### 基础部署（本地 Ollama）

```bash
docker-compose up -d
```

### 企业级部署（Milvus + vLLM + 监控）

```bash
# 启动完整栈：FastAPI + Milvus + etcd + minio + vLLM + Prometheus + Grafana
docker-compose -f docker-compose.yml up -d

# 查看各服务状态
docker-compose ps

# 查看 API 日志
docker-compose logs -f api
```

**访问地址：**
- API: http://localhost:8000
- Milvus: localhost:19530
- vLLM: http://localhost:8001
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

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
