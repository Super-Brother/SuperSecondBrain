"""构建索引脚本

用法:
  全量构建:   cd ~/projects/secondbrain-chat && source .venv/bin/activate && python scripts/build_index.py
  增量构建:   python scripts/build_index.py --incremental
"""

import os

# macOS MPS 内存分配器在模型预热时可能触发段错误，完全禁用 MPS 避免崩溃
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

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
    args = parser.parse_args()

    vault_path = os.getenv(
        "VAULT_PATH",
        "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    )
    index_dir = os.getenv("INDEX_DIR", str(ROOT / "data" / "index"))

    config = PipelineConfig(
        vault_path=vault_path,
        index_dir=index_dir,
        chunk_size=512,
        chunk_overlap=100,
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
