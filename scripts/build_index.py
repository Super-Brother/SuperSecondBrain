"""构建索引脚本

用法:
  全量构建:   cd ~/projects/secondbrain-chat && source .venv/bin/activate && python scripts/build_index.py
  增量构建:   python scripts/build_index.py --incremental
"""

import os

# macOS MPS 内存分配器在批量向量化时可能触发段错误；若显式启用 MPS，则保留上限。
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.7")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
# 避免 huggingface/tokenizers 在 fork 后启用并行导致死锁/段错误
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 限制 OpenMP 线程数，避免 CPU 上 embedding 时线程同步开销过大
os.environ.setdefault("OMP_NUM_THREADS", "4")
# 全量重建时使用 legacy 切分策略，避免语义切分对每个句子计算 embedding 导致极慢
os.environ.setdefault("SPLIT_STRATEGY", "legacy")
# 控制 embedding batch size，降低全量重建时的内存峰值
os.environ.setdefault("EMBEDDING_BATCH_SIZE", "32")
# 默认 CPU 更稳定；需要时可通过环境变量改为 mps/cuda。
os.environ.setdefault("EMBEDDING_DEVICE", "cpu")

# 关键：在 jieba 等多线程库之前先初始化 torch，
# 避免 PyTorch 线程状态与 jieba 多线程冲突导致的段错误 (macOS)
import torch  # noqa: F401

import argparse
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig


def main():
    parser = argparse.ArgumentParser(description="构建/更新知识库索引")
    parser.add_argument("--incremental", action="store_true", help="增量模式：只处理变更文件")
    parser.add_argument("--versioned", action="store_true", help="版本化模式：创建新版本并自动切换（保留旧版本支持回滚）")
    parser.add_argument(
        "--source-dir",
        default=None,
        help="多格式文档源目录（提供时调用 DocumentRouter 处理 .md/.pdf/.docx/.pptx/.xlsx）",
    )
    parser.add_argument(
        "--include-types",
        default="",
        help="限制处理的文件扩展名，逗号分隔，例如 .pdf,.docx,.pptx,.xlsx,.md",
    )
    args = parser.parse_args()

    vault_path = os.getenv(
        "VAULT_PATH",
        "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    )
    index_dir = os.getenv("INDEX_DIR", str(ROOT / "data" / "index"))

    # source-dir 优先级高于默认 vault_path，用于服务器多格式文档目录
    source_dir = args.source_dir or vault_path
    include_types = None
    if args.include_types:
        include_types = [t.strip() for t in args.include_types.split(",") if t.strip()]

    # 仅当显式提供 --source-dir 或 --include-types 时才走多格式路径，
    # 保持默认行为与旧版一致（Obsidian Markdown）。
    is_multiformat = args.source_dir is not None or bool(include_types)

    config = PipelineConfig(
        vault_path=vault_path,
        index_dir=index_dir,
        chunk_size=1024,
        chunk_overlap=200,
        versioned=args.versioned,
    )

    pipeline = SecondBrainPipeline(config)

    if is_multiformat:
        # 多格式路径：使用 DocumentRouter，支持 .md/.pdf/.docx/.pptx/.xlsx
        if args.incremental:
            index_file = os.path.join(index_dir, "faiss.index")
            documents_file = os.path.join(index_dir, "documents.pkl")
            bm25_file = os.path.join(index_dir, "bm25.pkl")
            if os.path.exists(index_file) and os.path.exists(documents_file) and os.path.exists(bm25_file):
                pipeline.load_index(index_dir)
        stats = pipeline.rebuild_index_from_vault(
            vault_path=source_dir,
            incremental=args.incremental,
            include_types=include_types,
        )
    else:
        # 默认 Obsidian 路径：只处理 Markdown
        if args.incremental:
            index_file = os.path.join(index_dir, "faiss.index")
            documents_file = os.path.join(index_dir, "documents.pkl")
            bm25_file = os.path.join(index_dir, "bm25.pkl")
            if os.path.exists(index_file) and os.path.exists(documents_file) and os.path.exists(bm25_file):
                pipeline.load_index(index_dir)
        stats = pipeline.build_index(incremental=args.incremental)

    import json
    mode = "增量" if args.incremental else "全量"
    path_label = "多格式" if is_multiformat else "Obsidian"
    print(f"\n{'='*50}")
    print(f"索引构建完成（{path_label} {mode}模式）！")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
