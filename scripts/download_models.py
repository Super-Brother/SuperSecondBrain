#!/usr/bin/env python3
"""预下载 Embedding 和 Reranker 模型到本地目录

用法:
    # 在有外网的机器上运行（自动使用国内镜像）
    export HF_ENDPOINT=https://hf-mirror.com
    python3 scripts/download_models.py

    # 然后上传 data/models/ 目录到服务器
    rsync -avz data/models/ user@server:/path/to/project/data/models/

环境变量:
    HF_ENDPOINT: HuggingFace 镜像地址（默认 https://hf-mirror.com）
"""

import os
import sys

# 默认使用国内镜像
if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from huggingface_hub import snapshot_download


def download_model(repo_id: str, local_dir: str, cache_dir: str = None):
    """下载模型到本地目录"""
    print(f"\n{'='*60}")
    print(f"下载模型: {repo_id}")
    print(f"目标目录: {os.path.abspath(local_dir)}")
    print(f"镜像地址: {os.getenv('HF_ENDPOINT')}")
    print(f"{'='*60}")

    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        print(f"✅ {repo_id} 下载完成")
        return True
    except Exception as e:
        print(f"❌ {repo_id} 下载失败: {e}")
        return False


def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "models")
    os.makedirs(base_dir, exist_ok=True)

    embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
    reranker_model = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")

    # 提取模型短名称作为目录名
    emb_name = embedding_model.replace("/", "_")
    rerank_name = reranker_model.replace("/", "_")

    emb_dir = os.path.join(base_dir, emb_name)
    rerank_dir = os.path.join(base_dir, rerank_name)

    results = []
    results.append(download_model(embedding_model, emb_dir))
    results.append(download_model(reranker_model, rerank_dir))

    print(f"\n{'='*60}")
    if all(results):
        print("✅ 所有模型下载完成！")
    else:
        print("⚠️ 部分模型下载失败，请检查网络连接")
    print(f"{'='*60}")
    print(f"\n模型目录: {os.path.abspath(base_dir)}")
    print(f"\n上传到服务器:")
    print(f"  rsync -avz {base_dir}/ user@your-server:/path/to/project/data/models/")
    print(f"\n然后修改 .env.server:")
    print(f"  EMBEDDING_MODEL=/app/data/models/{emb_name}")
    print(f"  RERANKER_MODEL=/app/data/models/{rerank_name}")


if __name__ == "__main__":
    main()
