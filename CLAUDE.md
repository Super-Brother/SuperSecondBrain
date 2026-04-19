# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SecondBrain Chat — 基于 RAG 的个人知识库智能问答系统，数据源来自 Obsidian 笔记本。

数据流：用户提问 → 混合检索(BM25+向量) → CrossEncoder Rerank → LLM生成 → 答案+来源引用

## Common Commands

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 构建/重建索引（从 Obsidian vault）
python scripts/build_index.py

# 启动 FastAPI 服务（API + 内嵌前端）
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# 启动 Gradio 前端（开发推荐）
python scripts/gradio_app.py

# 运行测试
pytest tests/ -v
```

## Architecture

### 核心流水线 (src/retrievers/pipeline.py)

`SecondBrainPipeline` 是端到端编排器，串联所有组件：

1. `ObsidianParser` 解析 vault 中所有 .md 文件
2. `split_notes_to_documents()` 切分为 LangChain Document chunks
3. `VectorRetriever` (FAISS + BGE-Large-ZH 768维) + `BM25Retriever` (jieba 分词)
4. `HybridRetriever` 加权融合两路分数（默认向量 0.7 / BM25 0.3）
5. `RAGRetriever` 调用 CrossEncoder (BGE-Reranker-Base) 精排
6. `LLMGenerator` 通过 OpenAI 兼容 API 调用 LLM 生成答案

### 模块职责

- **src/parsers/obsidian_parser.py**: 解析 YAML frontmatter、`[[]]`双向链接、标签、标题层级；`classify_domain()` 按文件夹名路由领域
- **src/parsers/text_splitter.py**: 中文优化的 RecursiveCharacterTextSplitter，分隔符优先级：二级标题→段落→中文句号→逗号
- **src/retrievers/rag_retriever.py**: 四个检索器类（Vector / BM25 / Hybrid / RAG），SearchConfig 控制权重和领域过滤
- **src/models/llm_generator.py**: OpenAI 兼容客户端，支持同步和流式生成，SYSTEM_PROMPT 定义助手行为约束
- **src/api/app.py**: FastAPI 端点 `/health` `/stats` `/api/v1/chat` `/api/v1/chat/stream` `/api/v1/domains`，启动时自动加载索引
- **scripts/**: `build_index.py` 构建索引，`gradio_app.py` Gradio 前端

### 关键设计

- **领域路由**: `obsidian_parser.py` 中的 `DOMAIN_MAP` 将 Obsidian 文件夹映射到领域（通识/AI-ML/编程/面试），检索时可按领域过滤
- **索引持久化**: FAISS 索引 (`faiss.index`) + pickle 序列化的 BM25 和 documents，存储在 `data/index/`
- **延迟加载**: Embedding 模型和 Reranker 通过 `@property` 延迟初始化，避免启动时加载大模型
- **环境变量**: 所有配置通过 `.env` 管理，见 `.env.example`

## Tech Stack

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| 前端 | Gradio / 内嵌 HTML |
| Embedding | BAAI/bge-large-zh-v1.5 (768d) |
| 向量数据库 | FAISS (IndexFlatIP, L2归一化=余弦相似度) |
| 关键词检索 | rank-bm25 + jieba |
| Reranker | BAAI/bge-reranker-base (CrossEncoder) |
| LLM | OpenAI 兼容 API (默认 Qwen2.5-3B) |
| RAG 编排 | LangChain (Document, TextSplitter) |
