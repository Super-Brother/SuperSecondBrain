"""测试 build_index.py CLI 入口"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _run_main(args: list[str], monkeypatch, tmp_path):
    """在 mock pipeline 下调用 build_index.py main"""
    vault = tmp_path / "vault"
    vault.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir(exist_ok=True)

    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("INDEX_DIR", str(index_dir))
    monkeypatch.setattr(sys, "argv", ["build_index.py"] + args)

    with patch("scripts.build_index.SecondBrainPipeline") as pipeline_cls:
        pipeline = MagicMock()
        pipeline.build_index.return_value = {"total_notes": 1}
        pipeline.rebuild_index_from_vault.return_value = {"total_notes": 2}
        pipeline_cls.return_value = pipeline

        # 动态导入以确保环境变量先被 monkeypatch
        import scripts.build_index as cli

        cli.main()
        return pipeline


def test_default_calls_obsidian_build_index(tmp_path, monkeypatch):
    pipeline = _run_main([], monkeypatch, tmp_path)
    pipeline.build_index.assert_called_once_with(incremental=False)
    pipeline.rebuild_index_from_vault.assert_not_called()


def test_incremental_loads_existing_index_for_obsidian(tmp_path, monkeypatch):
    index_dir = tmp_path / "index"
    index_dir.mkdir(exist_ok=True)
    (index_dir / "faiss.index").write_bytes(b"placeholder")
    (index_dir / "documents.pkl").write_bytes(b"placeholder")
    (index_dir / "bm25.pkl").write_bytes(b"placeholder")

    pipeline = _run_main(["--incremental"], monkeypatch, tmp_path)
    pipeline.load_index.assert_called_once_with(str(index_dir))
    pipeline.build_index.assert_called_once_with(incremental=True)


def test_source_dir_calls_multiformat_rebuild(tmp_path, monkeypatch):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()

    pipeline = _run_main(["--source-dir", str(source_dir)], monkeypatch, tmp_path)
    pipeline.build_index.assert_not_called()
    pipeline.rebuild_index_from_vault.assert_called_once_with(
        vault_path=str(source_dir),
        incremental=False,
        include_types=None,
    )


def test_source_dir_with_include_types(tmp_path, monkeypatch):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()

    pipeline = _run_main(
        ["--source-dir", str(source_dir), "--include-types", ".pdf,.docx"],
        monkeypatch,
        tmp_path,
    )
    pipeline.rebuild_index_from_vault.assert_called_once_with(
        vault_path=str(source_dir),
        incremental=False,
        include_types=[".pdf", ".docx"],
    )


def test_source_dir_incremental_loads_existing_index(tmp_path, monkeypatch):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir(exist_ok=True)
    (index_dir / "faiss.index").write_bytes(b"placeholder")
    (index_dir / "documents.pkl").write_bytes(b"placeholder")
    (index_dir / "bm25.pkl").write_bytes(b"placeholder")

    pipeline = _run_main(
        ["--source-dir", str(source_dir), "--incremental"],
        monkeypatch,
        tmp_path,
    )
    pipeline.load_index.assert_called_once_with(str(index_dir))
    pipeline.rebuild_index_from_vault.assert_called_once_with(
        vault_path=str(source_dir),
        incremental=True,
        include_types=None,
    )


def test_include_types_alone_uses_default_vault_path(tmp_path, monkeypatch):
    """只提供 --include-types 时，应使用默认 VAULT_PATH 作为 source_dir"""
    pipeline = _run_main(["--include-types", ".md"], monkeypatch, tmp_path)
    pipeline.rebuild_index_from_vault.assert_called_once_with(
        vault_path=str(tmp_path / "vault"),
        incremental=False,
        include_types=[".md"],
    )
