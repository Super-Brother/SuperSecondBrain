"""构建索引脚本

用法: cd ~/projects/secondbrain-chat && source .venv/bin/activate && python scripts/build_index.py
"""

import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig


def main():
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
    stats = pipeline.build_index()

    import json
    print(f"\n{'='*50}")
    print("索引构建完成！")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"{'='*50}")

    # 启动 FastAPI 服务
    print("\n💡 启动服务: cd ~/projects/secondbrain-chat && source .venv/bin/activate && uvicorn src.api.app:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
