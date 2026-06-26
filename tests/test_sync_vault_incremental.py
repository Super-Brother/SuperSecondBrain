"""测试服务器端 Git 增量索引同步脚本"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_vault_incremental import FileLock, SyncSummary, run_sync


class FakeLock(FileLock):
    """测试用锁，可预先标记为已占用"""

    def __init__(self, lock_path: Path, acquired: bool = True):
        super().__init__(lock_path)
        self.acquired = acquired

    def acquire(self, blocking: bool = True) -> bool:
        return self.acquired

    def release(self) -> None:
        pass


def _make_pipeline_class(rebuild_stats: dict | None = None):
    """构造一个用于注入的 mock Pipeline 类"""
    pipeline_cls = MagicMock()
    pipeline = MagicMock()
    pipeline.rebuild_index_from_vault.return_value = rebuild_stats or {
        "total_notes": 1,
        "total_chunks": 2,
    }
    pipeline_cls.return_value = pipeline
    return pipeline_cls, pipeline


def test_run_sync_returns_error_when_vault_missing(tmp_path):
    summary = run_sync(
        vault_path=str(tmp_path / "missing"),
        index_dir=str(tmp_path / "index"),
        lock=FakeLock(tmp_path / "index" / ".sync.lock"),
    )
    assert summary.status == "error"
    assert "does not exist" in summary.message


def test_run_sync_returns_locked_when_lock_held(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    summary = run_sync(
        vault_path=str(vault),
        index_dir=str(tmp_path / "index"),
        lock=FakeLock(tmp_path / "index" / ".sync.lock", acquired=False),
    )
    assert summary.status == "locked"
    assert "already running" in summary.message


def test_run_sync_no_change_skips_rebuild(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    index_dir = tmp_path / "index"
    vault.mkdir()
    index_dir.mkdir()
    (vault / ".git").mkdir()

    pipeline_cls, pipeline = _make_pipeline_class()

    with (
        patch("scripts.sync_vault_incremental.get_head", return_value="abc123"),
        patch("scripts.sync_vault_incremental.pull_vault") as pull,
        patch("scripts.sync_vault_incremental.changed_files_between") as diff,
    ):
        summary = run_sync(
            vault_path=str(vault),
            index_dir=str(index_dir),
            pipeline_class=pipeline_cls,
            lock=FakeLock(index_dir / ".sync.lock"),
        )

    assert summary.status == "no_change"
    assert summary.old_head == "abc123"
    assert summary.new_head == "abc123"
    pull.assert_called_once()
    pipeline_cls.assert_not_called()
    pipeline.rebuild_index_from_vault.assert_not_called()
    diff.assert_not_called()


def test_run_sync_head_change_triggers_incremental_rebuild(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    index_dir = tmp_path / "index"
    vault.mkdir()
    index_dir.mkdir()
    (vault / ".git").mkdir()

    pipeline_cls, pipeline = _make_pipeline_class(
        rebuild_stats={"total_notes": 3, "total_chunks": 5}
    )

    with (
        patch(
            "scripts.sync_vault_incremental.get_head",
            side_effect=["old_head", "new_head"],
        ),
        patch("scripts.sync_vault_incremental.pull_vault") as pull,
        patch(
            "scripts.sync_vault_incremental.changed_files_between",
            return_value=(["changed.md"], ["deleted.md"]),
        ) as diff,
    ):
        summary = run_sync(
            vault_path=str(vault),
            index_dir=str(index_dir),
            pipeline_class=pipeline_cls,
            lock=FakeLock(index_dir / ".sync.lock"),
        )

    assert summary.status == "success"
    assert summary.old_head == "old_head"
    assert summary.new_head == "new_head"
    assert summary.changed_files == ["changed.md"]
    assert summary.deleted_files == ["deleted.md"]
    assert summary.stats == {"total_notes": 3, "total_chunks": 5}
    pull.assert_called_once()
    pipeline.rebuild_index_from_vault.assert_called_once_with(incremental=True)
    diff.assert_called_once_with(str(vault), "old_head", "new_head")


def test_run_sync_no_git_no_sync_script_fails(tmp_path):
    vault = tmp_path / "vault"
    index_dir = tmp_path / "index"
    vault.mkdir()
    index_dir.mkdir()
    # 没有 .git，也没有提供 sync script

    pipeline_cls, _ = _make_pipeline_class()

    summary = run_sync(
        vault_path=str(vault),
        index_dir=str(index_dir),
        pipeline_class=pipeline_cls,
        lock=FakeLock(index_dir / ".sync.lock"),
    )

    assert summary.status == "error"
    assert "No sync method configured" in summary.message
    pipeline_cls.assert_not_called()


def test_run_sync_loads_existing_index_before_rebuild(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    index_dir = tmp_path / "index"
    vault.mkdir()
    index_dir.mkdir()
    (vault / ".git").mkdir()
    (index_dir / "faiss.index").write_bytes(b"placeholder")
    (index_dir / "documents.pkl").write_bytes(b"placeholder")
    (index_dir / "bm25.pkl").write_bytes(b"placeholder")

    pipeline_cls, pipeline = _make_pipeline_class()

    with (
        patch(
            "scripts.sync_vault_incremental.get_head",
            side_effect=["old_head", "new_head"],
        ),
        patch("scripts.sync_vault_incremental.pull_vault"),
        patch(
            "scripts.sync_vault_incremental.changed_files_between",
            return_value=(["changed.md"], []),
        ),
    ):
        run_sync(
            vault_path=str(vault),
            index_dir=str(index_dir),
            pipeline_class=pipeline_cls,
            lock=FakeLock(index_dir / ".sync.lock"),
        )

    pipeline.load_index.assert_called_once_with(str(index_dir))
    pipeline.rebuild_index_from_vault.assert_called_once_with(incremental=True)


def test_sync_summary_is_serializable():
    summary = SyncSummary(
        status="success",
        old_head="a",
        new_head="b",
        changed_files=["x.md"],
        deleted_files=["y.md"],
        stats={"total_notes": 1},
        duration_seconds=1.23,
        message="ok",
    )
    data = summary.__dict__
    assert data["status"] == "success"
    assert data["changed_files"] == ["x.md"]
