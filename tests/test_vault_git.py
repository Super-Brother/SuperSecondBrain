from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.vault_git import (
    GitSyncError,
    changed_files_between,
    commit_and_push_vault_change,
    get_head,
    pull_vault,
)


def _completed(returncode=0, stdout="ok", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_pull_vault_uses_custom_script(tmp_path):
    script = tmp_path / "sync.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with patch("src.utils.vault_git.subprocess.run", return_value=_completed(stdout="script ok")) as run:
        result = pull_vault(str(tmp_path), sync_script_path=str(script))

    assert result.stdout == "script ok"
    run.assert_called_once_with([str(script)], capture_output=True, text=True, timeout=120)


def test_pull_vault_uses_git_pull_when_vault_is_repo(tmp_path):
    (tmp_path / ".git").mkdir()

    with patch("src.utils.vault_git.subprocess.run", return_value=_completed(stdout="pulled")) as run:
        result = pull_vault(str(tmp_path), sync_script_path="")

    assert result.stdout == "pulled"
    run.assert_called_once_with(["git", "-C", str(tmp_path), "pull"], capture_output=True, text=True, timeout=120)


def test_pull_vault_raises_without_sync_method(tmp_path):
    try:
        pull_vault(str(tmp_path), sync_script_path="")
        assert False, "expected GitSyncError"
    except GitSyncError as exc:
        assert "No sync method configured" in str(exc)


def test_commit_and_push_skips_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("VAULT_GIT_WRITEBACK", raising=False)
    result = commit_and_push_vault_change(str(tmp_path), "create", "note.md")
    assert result.skipped is True


def test_commit_and_push_runs_expected_git_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_GIT_WRITEBACK", "true")
    (tmp_path / ".git").mkdir()

    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=120):
        calls.append(cmd)
        if cmd[-1] == "status":
            return _completed(stdout=" M note.md")
        return _completed(stdout="ok")

    with patch("src.utils.vault_git.subprocess.run", side_effect=fake_run):
        result = commit_and_push_vault_change(str(tmp_path), "update", "note.md")

    assert result.skipped is False
    assert ["git", "-C", str(tmp_path), "add", "--", "note.md"] in calls
    assert ["git", "-C", str(tmp_path), "pull", "--rebase"] in calls
    assert ["git", "-C", str(tmp_path), "push"] in calls


def test_commit_and_push_raises_on_rebase_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_GIT_WRITEBACK", "true")
    (tmp_path / ".git").mkdir()

    def fake_run(cmd, capture_output=True, text=True, timeout=120):
        if cmd[-1] == "status":
            return _completed(stdout=" M note.md")
        if cmd[-2:] == ["pull", "--rebase"]:
            return _completed(returncode=1, stderr="CONFLICT")
        return _completed(stdout="ok")

    try:
        with patch("src.utils.vault_git.subprocess.run", side_effect=fake_run):
            commit_and_push_vault_change(str(tmp_path), "update", "note.md")
        assert False, "expected GitSyncError"
    except GitSyncError as exc:
        assert "CONFLICT" in str(exc)


def test_get_head_returns_rev_parse_output(tmp_path):
    (tmp_path / ".git").mkdir()

    with patch("src.utils.vault_git.subprocess.run", return_value=_completed(stdout="abc1234\n")) as run:
        head = get_head(str(tmp_path))

    assert head == "abc1234"
    run.assert_called_once_with(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_get_head_raises_when_not_git_repo(tmp_path):
    try:
        get_head(str(tmp_path))
        assert False, "expected GitSyncError"
    except GitSyncError as exc:
        assert "not a git repository" in str(exc)


def test_changed_files_between_parses_name_status(tmp_path):
    (tmp_path / ".git").mkdir()

    diff_output = "M\tmodified.md\nA\tadded.md\nD\tdeleted.md\nR100\told.md\tnew.md\n"

    with patch("src.utils.vault_git.subprocess.run", return_value=_completed(stdout=diff_output)) as run:
        changed, deleted = changed_files_between(str(tmp_path), "old", "new")

    assert set(changed) == {"modified.md", "added.md", "new.md"}
    assert deleted == ["deleted.md"]
    run.assert_called_once_with(
        ["git", "-C", str(tmp_path), "diff", "--name-status", "old", "new"],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_changed_files_between_returns_empty_for_same_head(tmp_path):
    (tmp_path / ".git").mkdir()
    changed, deleted = changed_files_between(str(tmp_path), "same", "same")
    assert changed == []
    assert deleted == []


def test_changed_files_between_raises_when_not_git_repo(tmp_path):
    try:
        changed_files_between(str(tmp_path), "old", "new")
        assert False, "expected GitSyncError"
    except GitSyncError as exc:
        assert "not a git repository" in str(exc)
