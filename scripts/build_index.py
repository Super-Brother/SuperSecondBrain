"""构建索引脚本

用法:
  全量构建:   cd ~/projects/secondbrain-chat && source .venv/bin/activate && python scripts/build_index.py
  增量构建:   python scripts/build_index.py --incremental
"""

import os

# macOS MPS 内存分配器在模型预热时可能触发段错误，完全禁用 MPS 避免崩溃
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
# 避免 huggingface/tokenizers 在 fork 后启用并行导致死锁/段错误
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 限制 OpenMP 线程数，避免 CPU 上 embedding 时线程同步开销过大
os.environ.setdefault("OMP_NUM_THREADS", "4")
# 全量重建时使用 legacy 切分策略，避免语义切分对每个句子计算 embedding 导致极慢
os.environ.setdefault("SPLIT_STRATEGY", "legacy")
# 增大 embedding batch size，提升 CPU 上编码吞吐量
os.environ.setdefault("EMBEDDING_BATCH_SIZE", "64")
# 在 Apple Silicon 上尝试使用 MPS 加速 embedding（失败会自动报错，可改回 cpu）
os.environ.setdefault("EMBEDDING_DEVICE", "mps")

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
    args = parser.parse_args()

    vault_path = os.getenv(
        "VAULT_PATH",
        "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    )
    index_dir = os.getenv("INDEX_DIR", str(ROOT / "data" / "index"))

    config = PipelineConfig(
        vault_path=vault_path,
        index_dir=index_dir,
        chunk_size=1024,
        chunk_overlap=200,
        versioned=args.versioned,
    )

    pipeline = SecondBrainPipeline(config)
    stats = pipeline.build_index(incremental=args.incremental)

    import json
    mode = "增量" if args.incremental else "全量"
    print(f"\n{'='*50}")
    print(f"索引构建完成（{mode}模式）！")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
