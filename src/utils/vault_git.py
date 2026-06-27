"""Git helpers for server-side Vault synchronization."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitSyncError(RuntimeError):
    """Raised when Vault Git synchronization fails."""


@dataclass
class GitSyncResult:
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False


def _run(cmd: list[str], timeout: int = 120) -> GitSyncResult:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise GitSyncError(result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}")
    return GitSyncResult(stdout=result.stdout, stderr=result.stderr)


def pull_vault(vault_path: str, sync_script_path: str = "") -> GitSyncResult:
    vault = Path(vault_path)
    if sync_script_path and Path(sync_script_path).exists():
        return _run([sync_script_path])
    if (vault / ".git").exists():
        return _run(["git", "-C", str(vault), "pull", "--ff-only"])
    raise GitSyncError("No sync method configured. Set SYNC_SCRIPT_PATH or ensure vault is a git repo.")


def get_head(vault_path: str) -> str:
    """获取 vault Git 仓库当前 HEAD commit hash。"""
    vault = Path(vault_path)
    if not (vault / ".git").exists():
        raise GitSyncError(f"Vault path is not a git repository: {vault_path}")
    result = _run(["git", "-C", str(vault), "rev-parse", "HEAD"])
    head = result.stdout.strip()
    if not head:
        raise GitSyncError(f"Failed to resolve HEAD for vault: {vault_path}")
    return head


def changed_files_between(
    vault_path: str, old_head: str, new_head: str
) -> tuple[list[str], list[str]]:
    """比较两个 commit，返回 (变更文件列表, 删除文件列表)。

    变更包含新增、修改、重命名/复制的目标路径；删除包含被移除的文件路径。
    """
    vault = Path(vault_path)
    if not (vault / ".git").exists():
        raise GitSyncError(f"Vault path is not a git repository: {vault_path}")
    if old_head == new_head:
        return [], []

    result = _run(["git", "-C", str(vault), "diff", "--name-status", old_head, new_head])
    changed: list[str] = []
    deleted: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("D"):
            deleted.append(parts[1])
        elif status.startswith(("R", "C")):
            # 重命名/复制：新路径在最后一段
            changed.append(parts[-1])
        else:
            changed.append(parts[1])
    return changed, deleted


def _writeback_enabled() -> bool:
    return os.getenv("VAULT_GIT_WRITEBACK", "false").lower() in {"true", "1", "yes"}


def commit_and_push_vault_change(vault_path: str, action: str, relative_path: str) -> GitSyncResult:
    if not _writeback_enabled():
        return GitSyncResult(skipped=True)

    vault = Path(vault_path)
    if not (vault / ".git").exists():
        raise GitSyncError("VAULT_GIT_WRITEBACK=true requires VAULT_PATH to be a git repository.")

    status = _run(["git", "-C", str(vault), "status", "--porcelain", "--", relative_path])
    if not status.stdout.strip():
        return GitSyncResult(skipped=True)

    _run(["git", "-C", str(vault), "add", "--", relative_path])
    _run(["git", "-C", str(vault), "commit", "-m", f"notes: {action} {relative_path}"])
    _run(["git", "-C", str(vault), "pull", "--rebase"])
    push = _run(["git", "-C", str(vault), "push"])
    return GitSyncResult(stdout=push.stdout, stderr=push.stderr)
