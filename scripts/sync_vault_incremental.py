"""服务器端 Git 增量索引同步脚本。

用法:
  由 systemd timer 或 cron 调用:
    cd ~/projects/secondbrain-chat && conda run -n secondbrain-chat python scripts/sync_vault_incremental.py

环境变量:
  VAULT_PATH        vault 目录（必须是 git 仓库或配合 SYNC_SCRIPT_PATH）
  INDEX_DIR         索引保存目录
  SYNC_SCRIPT_PATH  可选：自定义同步脚本（优先于 git pull）
"""

from __future__ import annotations

import os

# 与 build_index.py 保持一致的 embedding 稳定性默认值
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.7")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("SPLIT_STRATEGY", "legacy")
os.environ.setdefault("EMBEDDING_BATCH_SIZE", "32")
os.environ.setdefault("EMBEDDING_DEVICE", "cpu")

# 关键：在 jieba 等多线程库之前先初始化 torch，避免线程状态冲突
import torch  # noqa: F401

import argparse
import fcntl
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Type

# 项目根目录
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.pipeline import PipelineConfig, SecondBrainPipeline
from src.utils.vault_git import changed_files_between, get_head, pull_vault


@dataclass
class SyncSummary:
    """同步结果摘要"""

    status: str = "unknown"
    old_head: str = ""
    new_head: str = ""
    changed_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    duration_seconds: float = 0.0
    message: str = ""


class FileLock:
    """基于 flock 的进程级文件锁"""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fd = None

    def acquire(self, blocking: bool = True) -> bool:
        """获取锁；blocking=False 时若锁被占用立即返回 False。"""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self.lock_path, "w", encoding="utf-8")
        try:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(self._fd.fileno(), flags)
            return True
        except (OSError, BlockingIOError):
            self._fd.close()
            self._fd = None
            return False

    def release(self) -> None:
        """释放锁"""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            finally:
                self._fd.close()
                self._fd = None


def _index_exists(index_dir: Path) -> bool:
    """判断目录中是否包含完整索引文件"""
    return (
        (index_dir / "faiss.index").exists()
        and (index_dir / "documents.pkl").exists()
        and (index_dir / "bm25.pkl").exists()
    )


def run_sync(
    vault_path: str,
    index_dir: str,
    sync_script_path: str = "",
    pipeline_class: Type[SecondBrainPipeline] = SecondBrainPipeline,
    lock: FileLock | None = None,
) -> SyncSummary:
    """执行一次增量同步。

    Args:
        vault_path: vault 目录
        index_dir: 索引目录
        sync_script_path: 可选自定义同步脚本
        pipeline_class: 用于测试注入的 Pipeline 类
        lock: 用于测试注入的锁对象
    """
    start = time.time()
    summary = SyncSummary()
    vault = Path(vault_path)
    index = Path(index_dir)

    if not vault.exists():
        summary.status = "error"
        summary.message = f"VAULT_PATH does not exist: {vault_path}"
        summary.duration_seconds = time.time() - start
        return summary

    lock = lock or FileLock(index / ".sync.lock")
    if not lock.acquire(blocking=False):
        summary.status = "locked"
        summary.message = "Another sync is already running"
        summary.duration_seconds = time.time() - start
        return summary

    try:
        # 记录同步前 HEAD；vault 不是 git 仓库时留空
        old_head = ""
        if (vault / ".git").exists():
            old_head = get_head(str(vault))

        # 拉取 vault 或执行自定义同步脚本
        pull_vault(str(vault), sync_script_path=sync_script_path)

        # 检查 HEAD 是否变化
        new_head = ""
        if (vault / ".git").exists():
            new_head = get_head(str(vault))

        summary.old_head = old_head
        summary.new_head = new_head

        if old_head and new_head and old_head == new_head:
            summary.status = "no_change"
            summary.message = "HEAD unchanged, skipped rebuild"
            summary.duration_seconds = time.time() - start
            return summary

        # 计算变更文件清单
        if old_head and new_head:
            changed, deleted = changed_files_between(str(vault), old_head, new_head)
            summary.changed_files = changed
            summary.deleted_files = deleted

        # 构造 pipeline；若已有索引则加载，以复用内存中的向量/BM25
        config = PipelineConfig(
            vault_path=str(vault),
            index_dir=str(index),
            chunk_size=1024,
            chunk_overlap=200,
        )
        pipeline = pipeline_class(config)
        if _index_exists(index):
            pipeline.load_index(str(index))

        # 触发多格式增量重建
        stats = pipeline.rebuild_index_from_vault(incremental=True)
        summary.status = "success"
        summary.stats = stats or {}
        summary.duration_seconds = time.time() - start
        return summary

    except Exception as exc:
        summary.status = "error"
        summary.message = str(exc)
        summary.duration_seconds = time.time() - start
        return summary
    finally:
        lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="服务器端 Git 增量索引同步")
    parser.add_argument("--vault", default=os.getenv("VAULT_PATH"), help="vault 目录")
    parser.add_argument("--index-dir", default=os.getenv("INDEX_DIR"), help="索引目录")
    parser.add_argument(
        "--sync-script",
        default=os.getenv("SYNC_SCRIPT_PATH", ""),
        help="可选：自定义同步脚本路径",
    )
    args = parser.parse_args()

    vault_path = args.vault
    index_dir = args.index_dir or str(ROOT / "data" / "index")
    sync_script_path = args.sync_script or ""

    if not vault_path:
        print(
            json.dumps(
                {"status": "error", "message": "VAULT_PATH is required"},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    summary = run_sync(vault_path, index_dir, sync_script_path)
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))
    if summary.status in ("error", "locked"):
        sys.exit(1)


if __name__ == "__main__":
    main()
