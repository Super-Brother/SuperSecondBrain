# SecondBrain Chat

基于 RAG 的个人知识库智能问答系统，驱动数据来自 Obsidian 笔记本。

## 架构

```
用户提问 → Query理解 → 混合检索(BM25+向量) → Rerank重排 → Prompt构建 → LLM生成 → 答案+来源
```

## 核心特性

- **混合检索**：BM25 关键词匹配 + 向量语义检索，分数加权融合
- **Rerank 重排序**：Cross-Encoder 精排，提升 Top-K 准确率
- **Obsidian 深度解析**：处理 frontmatter、[[]] 双向链接、标签、标题层级
- **多领域路由**：自动按文件夹分类（通识/AI/编程/面试），支持领域过滤
- **来源追溯**：每个回答标注来自哪篇笔记的哪部分

## 技术栈

| 组件 | 技术 |
|------|------|
| Web框架 | FastAPI |
| 前端 | Gradio |
| Embedding | BGE-Large-ZH (768维) |
| 向量数据库 | FAISS |
| 关键词检索 | BM25 + jieba |
| Reranker | BGE-Reranker-Base |
| LLM | Qwen2.5-3B (本地OpenAI兼容API) |
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
```

### 4. 启动服务

```bash
# Gradio 前端（推荐开发时使用）
python scripts/gradio_app.py

# 或 FastAPI API
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 知识库统计 |
| GET | `/api/v1/domains` | 领域列表 |
| POST | `/api/v1/chat` | 对话（非流式） |
| POST | `/api/v1/chat/stream` | 对话（SSE 流式） |

## 项目结构

```
secondbrain-chat/
├── data/
│   └── index/              # 构建好的索引文件
├── src/
│   ├── parsers/
│   │   ├── obsidian_parser.py   # Obsidian 笔记解析器
│   │   └── text_splitter.py     # 文档切分器
│   ├── retrievers/
│   │   ├── rag_retriever.py     # 检索器（向量/BM25/混合/Rerank）
│   │   └── pipeline.py          # RAG Pipeline（端到端）
│   ├── models/
│   │   └── llm_generator.py     # LLM 生成器
│   └── api/
│       └── app.py               # FastAPI 应用
├── scripts/
│   ├── build_index.py           # 索引构建脚本
│   └── gradio_app.py            # Gradio 前端
├── .env.example
├── requirements.txt
└── README.md
```

## License

MIT
