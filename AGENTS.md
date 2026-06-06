# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

SecondBrain Chat — 基于 RAG 的知识库智能问答系统，支持多格式文档（Obsidian / PDF / Word / PPT / Excel）。

数据流：用户提问 → Query脱敏 → 混合检索(BM25+向量) → 权限过滤 → CrossEncoder Rerank → LLM生成 → 答案脱敏 → 答案+来源引用

## Python Environment

Use the Conda environment `secondbrain-chat` for local development and command execution.

## Common Commands

```bash
# 激活 Python 环境
conda activate secondbrain-chat

# 安装依赖
pip install -r requirements.txt

# 构建/重建索引（从 Obsidian vault）
python scripts/build_index.py

# 从多格式文档目录构建索引（企业级）
python scripts/build_index.py --source-dir /path/to/docs --include-types .pdf .docx .md

# 启动 FastAPI 服务（API + 内嵌前端）
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# 启动 Gradio 前端（开发推荐）
python scripts/gradio_app.py

# 运行测试
pytest tests/ -v

# 运行自动化评估
python -c "from src.evaluation import RAGEvaluator; RAGEvaluator()"

# Docker 轻量部署（推荐）
docker-compose up -d

# Docker 服务器部署（FAISS + Redis，国内镜像源优化）
docker compose -f docker-compose.server.yml up -d

# 一键服务器部署脚本（含代理检测、索引构建）
./deploy_server.sh

# Docker 企业级完整部署（含 Milvus + vLLM）
docker-compose -f docker-compose.full.yml up -d
```

## Architecture

### RAG 全链路三阶段

| 阶段 | 链路 | 状态 |
|------|------|------|
| ① 离线索引 | `原始文档 → DocumentRouter解析 → 文本切片 → Embedding → FAISS/Milvus` | ✅ 完整实现 |
| ② 在线检索 | `Query改写+脱敏 → Hybrid检索(向量+BM25) → 权限过滤 → CrossEncoder Rerank` | ✅ 完整实现 |
| ③ 生成 | `Prompt构建(上下文+历史) → LLM生成 → 答案脱敏 → 带来源引用返回` | ✅ 完整实现 |

**已知缺口（按优先级排序）：**
1. **多轮对话压缩** — 历史只取最近 20 条，无摘要压缩机制，长对话易超上下文窗口
2. **分布式缓存** — `ResponseCache` 为内存 LRU，无 Redis 后端
3. **限流熔断** — 无 API rate limiting，LLM 调用费用不可控
4. **日志审计** — 只有基础 access log，无操作审计和 ELK 聚合

### 核心流水线 (src/retrievers/pipeline.py)

`SecondBrainPipeline` 是端到端编排器，串联所有组件：

1. `DocumentRouter` 根据文件扩展名路由到对应解析器（Obsidian / Markdown / PDF / Word / PPT / Excel）
2. `split_notes_to_documents()` 切分为 LangChain Document chunks
3. `VectorRetriever` (FAISS / Milvus 可插拔) + `BM25Retriever` (jieba 分词)
4. `HybridRetriever` 加权融合两路分数（默认向量 0.7 / BM25 0.3），支持 RRF 融合
5. `RAGRetriever` 调用 CrossEncoder (BGE-Reranker-Base) 精排
6. `LLMGenerator` 通过 OpenAI 兼容 API 调用 LLM 生成答案
7. `QuerySanitizer` / `AnswerSanitizer` 三级数据脱敏

### 模块职责

- **src/parsers/obsidian_parser.py**: 解析 YAML frontmatter、`[[]]`双向链接、标签、标题层级；`classify_domain()` 按文件夹名路由领域
- **src/parsers/markdown_parser.py**: 通用 Markdown 解析，无 Obsidian 特殊处理
- **src/parsers/pdf_parser.py**: PDF 解析（PyMuPDF），支持文本提取和元数据读取
- **src/parsers/office_parser.py**: Word / PPT / Excel 解析（python-docx / python-pptx / openpyxl）
- **src/parsers/document_router.py**: 根据文件扩展名自动路由到对应解析器，统一输出 Document 列表
- **src/parsers/text_splitter.py**: 中文优化的 RecursiveCharacterTextSplitter，分隔符优先级：二级标题→段落→中文句号→逗号
- **src/retrievers/rag_retriever.py**: 四个检索器类（Vector / BM25 / Hybrid / RAG），`SearchConfig` 控制权重、领域过滤、权限过滤（`user_departments` / `user_access_level`）
- **src/retrievers/vector_store/base.py**: 向量存储抽象基类 `VectorStore`，定义统一接口：`add_documents` / `delete_by_filter` / `search` / `save` / `load`
- **src/retrievers/vector_store/faiss_store.py**: FAISS 本地实现，完全向后兼容
- **src/retrievers/vector_store/milvus_store.py**: Milvus 分布式实现，支持元数据过滤（`department` / `access_level`）和增量更新
- **src/models/llm_generator.py**: OpenAI 兼容客户端，支持同步和流式生成，SYSTEM_PROMPT 定义助手行为约束
- **src/utils/sanitizer.py**: 数据脱敏（Query / Document / Answer），支持手机号、身份证号、邮箱、银行卡号
- **src/evaluation/rag_evaluator.py**: RAGAS 自动化评估 + 启发式降级评估，指标：faithfulness / answer_relevancy / context_recall / context_precision
- **src/utils/metrics.py**: Prometheus 风格指标收集，支持延迟分位数（P50/P95/P99）、Token 使用量、成功率
- **src/utils/vault_watcher.py**: watchdog 文件监控器，监听 vault 目录变更自动触发增量索引重建；防抖（默认 5s）、过滤非文档文件、线程安全加锁
- **src/api/app.py**: FastAPI 端点 `/health` `/stats` `/api/v1/chat` `/api/v1/chat/stream` `/api/v1/domains` `/api/v1/sync/webhook` `/api/v1/sync/trigger` `/api/v1/documents/upload` `/api/v1/documents/batch-upload`，启动时自动加载索引
- **scripts/**: `build_index.py` 构建索引，`gradio_app.py` Gradio 前端

### 关键设计

- **文档路由**: `document_router.py` 的 `PARSER_MAP` 将文件扩展名映射到解析器类，支持 `.md` `.pdf` `.docx` `.pptx` `.xlsx`
- **向量存储可插拔**: `VECTOR_STORE_BACKEND` 环境变量切换 FAISS / Milvus，接口完全一致
- **权限隔离**: Milvus 通过服务端元数据过滤表达式实现；FAISS 通过内存过滤实现兼容
- **领域路由**: `obsidian_parser.py` 中的 `DOMAIN_MAP` 将 Obsidian 文件夹映射到领域（通识/AI-ML/编程/面试），检索时可按领域过滤
- **索引持久化**: FAISS 索引 (`faiss.index`) + pickle 序列化的 BM25 和 documents，存储在 `data/index/`；Milvus 数据持久化在服务端
- **延迟加载**: Embedding 模型和 Reranker 通过 `@property` 延迟初始化，避免启动时加载大模型
- **数据脱敏**: 三级脱敏架构，可在 `.env` 中独立开关 Query / Document / Answer 脱敏
- **Vault 自动同步**: `AUTO_SYNC=true` 启用 watchdog 监听 vault 目录，文件变更后防抖触发增量索引重建（`AUTO_SYNC_DEBOUNCE` 控制延迟），排除 `.obsidian/.trash/.git` 等目录
- **服务器轻量部署**: `docker-compose.server.yml` 使用 FAISS + Redis，Dockerfile 配置国内镜像源（清华 PyPI + 阿里云 Debian），`deploy_server.sh` 一键部署含代理检测
- **环境变量**: 所有配置通过 `.env` 管理，见 `.env.example`

## Tech Stack

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| 前端 | Gradio / Streamlit / 内嵌 HTML |
| 文档解析 | PyMuPDF / python-docx / python-pptx / openpyxl |
| Embedding | BAAI/bge-large-zh-v1.5 (1024d) |
| 向量数据库 | FAISS (IndexFlatIP, L2归一化=余弦相似度) / Milvus (HNSW, 分布式) |
| 关键词检索 | rank-bm25 + jieba |
| Reranker | BAAI/bge-reranker-base (CrossEncoder) |
| LLM | OpenAI 兼容 API (默认 Qwen2.5-3B，可升级至 72B via vLLM) |
| RAG 编排 | LangChain (Document, TextSplitter) |
| 监控 | Prometheus + Grafana |
| 评估 | RAGAS + 启发式降级 |
| 部署 | Docker Compose |
