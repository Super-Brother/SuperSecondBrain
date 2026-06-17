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
        return _run(["git", "-C", str(vault), "pull"])
    raise GitSyncError("No sync method configured. Set SYNC_SCRIPT_PATH or ensure vault is a git repo.")


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
