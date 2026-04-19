# SecondBrain Chat

基于 RAG 的个人知识库智能问答系统，驱动数据来自 Obsidian 笔记本。

## 架构

```
用户提问 → Query改写 → 混合检索(BM25+向量) → Rerank重排 → Prompt构建 → LLM生成 → 答案+来源
```

## 核心特性

- **多轮对话记忆** — 基于 SQLite 的会话管理，支持上下文追问
- **增量索引** — 文件变更检测，只重建变更部分
- **查询改写** — LLM 将口语化查询转为检索关键词
- **混合检索** — BM25 关键词匹配 + 向量语义检索，分数加权融合
- **Rerank 重排序** — Cross-Encoder 精排，提升 Top-K 准确率
- **响应缓存** — LRU 缓存重复查询，毫秒级响应
- **Token 追踪** — 统计 LLM 用量
- **API Key 认证** — 可选的安全认证

## 技术栈

| 组件 | 技术 |
|------|------|
| Web框架 | FastAPI |
| 前端 | Streamlit / Gradio / 内嵌 HTML |
| Embedding | BAAI/bge-large-zh-v1.5 (768维) |
| 向量数据库 | FAISS |
| 关键词检索 | rank-bm25 + jieba |
| Reranker | BAAI/bge-reranker-base |
| LLM | OpenAI 兼容 API (默认 Qwen2.5-3B) |
| RAG编排 | LangChain |

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
# 编辑 .env 配置你的 LLM 地址
```

### 3. 构建索引（首次运行）

```bash
python scripts/build_index.py

# 增量更新
python scripts/build_index.py --incremental
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
│   ├── parsers/           # 解析器
│   │   ├── base_parser.py      # 抽象接口
│   │   ├── obsidian_parser.py  # Obsidian 解析
│   │   ├── markdown_parser.py  # 通用 Markdown
│   │   └── pdf_parser.py       # PDF 解析
│   ├── retrievers/        # 检索器
│   │   ├── rag_retriever.py    # 向量/BM25/混合/Rerank
│   │   ├── pipeline.py         # RAG Pipeline
│   │   └── query_rewriter.py   # 查询改写
│   ├── models/            # 模型
│   │   ├── llm_generator.py    # LLM 生成器
│   │   └── conversation.py     # 会话管理
│   ├── utils/             # 工具
│   │   ├── logger.py           # 日志
│   │   └── cache.py            # 响应缓存
│   └── api/               # API
│       ├── app.py              # FastAPI 应用
│       ├── auth.py             # 认证中间件
│       └── static.py           # 内嵌前端
├── scripts/
│   ├── build_index.py          # 索引构建
│   ├── streamlit_app.py        # Streamlit 前端
│   └── gradio_app.py           # Gradio 前端
├── tests/                 # 测试
├── data/index/            # 索引文件
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f app
```

## 测试

```bash
pytest tests/ -v --cov=src
```

## License

MIT
