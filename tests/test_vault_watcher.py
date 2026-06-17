"""测试 VaultWatcher 文件监控器"""

import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.vault_watcher import VaultEventHandler, VaultWatcher


class TestVaultEventHandler:
    def test_md_file_should_handle(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/笔记.md"
        assert handler._should_handle(event) is True

    def test_non_md_file_ignored(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/image.png"
        assert handler._should_handle(event) is False

    def test_pdf_file_should_handle(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/document.pdf"
        assert handler._should_handle(event) is True

    def test_docx_file_should_handle(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/report.docx"
        assert handler._should_handle(event) is True

    def test_pptx_file_should_handle(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/slides.pptx"
        assert handler._should_handle(event) is True

    def test_xlsx_file_should_handle(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/data.xlsx"
        assert handler._should_handle(event) is True

    def test_directory_ignored(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/vault/文件夹"
        assert handler._should_handle(event) is False

    def test_obsidian_dir_ignored(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/.obsidian/workspace.json"
        assert handler._should_handle(event) is False

    def test_trash_dir_ignored(self):
        handler = VaultEventHandler(MagicMock())
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/vault/.trash/旧笔记.md"
        assert handler._should_handle(event) is False


class TestVaultWatcher:
    def test_start_stop_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.1)

            assert watcher.is_running is False

            watcher.start()
            assert watcher.is_running is True
            assert watcher.stats["is_running"] is True

            watcher.stop()
            assert watcher.is_running is False

    def test_start_on_nonexistent_path_raises(self):
        pipeline = MagicMock()
        watcher = VaultWatcher("/nonexistent/path", pipeline)

        try:
            watcher.start()
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_double_start_is_safe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.1)
            watcher.start()
            watcher.start()  # 不应报错
            watcher.stop()

    def test_file_creation_triggers_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.return_value = {
                "total_notes": 1,
                "total_chunks": 1,
            }

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            # 创建文件
            Path(tmpdir, "test.md").write_text("# 测试", encoding="utf-8")
            time.sleep(0.5)  # 等待防抖+重建

            watcher.stop()

            # 验证增量重建被调用
            pipeline.build_index.assert_called_once_with(incremental=True)
            pipeline.rebuild_index_from_vault.assert_not_called()
            assert watcher._rebuild_count == 1

    def test_debounce_combines_multiple_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 1, "total_chunks": 1}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.3)
            watcher.start()

            # 快速连续创建多个文件
            for i in range(3):
                Path(tmpdir, f"note{i}.md").write_text(f"# 笔记{i}", encoding="utf-8")
                time.sleep(0.1)  # 在防抖时间内

            time.sleep(0.6)  # 等待防抖结束后重建

            watcher.stop()

            # 应该只触发一次重建
            assert pipeline.build_index.call_count == 1
            assert watcher._rebuild_count == 1

    def test_file_modification_triggers_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir, "existing.md")
            md_file.write_text("# 原始内容", encoding="utf-8")

            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 1, "total_chunks": 1}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            # 修改文件
            md_file.write_text("# 修改后的内容", encoding="utf-8")
            time.sleep(0.5)

            watcher.stop()

            pipeline.build_index.assert_called_once_with(incremental=True)

    def test_pdf_file_triggers_rebuild(self):
        """测试 PDF 文件变更触发重建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 1, "total_chunks": 1}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            # 创建 PDF 文件
            Path(tmpdir, "document.pdf").write_bytes(b"fake pdf content")
            time.sleep(0.5)

            watcher.stop()

            # 验证全量重建被触发
            pipeline.rebuild_index_from_vault.assert_called_once_with()
            pipeline.build_index.assert_not_called()
            assert watcher._rebuild_count == 1

    def test_file_deletion_triggers_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir, "to_delete.md")
            md_file.write_text("# 将被删除", encoding="utf-8")

            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 0, "total_chunks": 0}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            # 删除文件
            md_file.unlink()
            time.sleep(0.5)

            watcher.stop()

            pipeline.build_index.assert_called_once_with(incremental=True)

    def test_non_md_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 1, "total_chunks": 1}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            # 创建非 md 文件
            Path(tmpdir, "config.json").write_text("{}", encoding="utf-8")
            time.sleep(0.5)

            watcher.stop()

            # 不应触发重建
            pipeline.build_index.assert_not_called()

    def test_rebuild_failure_keeps_watcher_alive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.side_effect = RuntimeError("模拟重建失败")

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.2)
            watcher.start()

            Path(tmpdir, "test.md").write_text("# 测试", encoding="utf-8")
            time.sleep(0.5)

            # watcher 仍在运行
            assert watcher.is_running is True
            watcher.stop()

    def test_stats_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MagicMock()
            pipeline.build_index.return_value = {"total_notes": 2, "total_chunks": 5}

            watcher = VaultWatcher(tmpdir, pipeline, debounce_seconds=0.1)
            watcher.start()

            Path(tmpdir, "a.md").write_text("# A", encoding="utf-8")
            time.sleep(0.4)

            stats = watcher.stats
            assert stats["rebuild_count"] == 1
            assert stats["is_running"] is True
            assert stats["vault_path"] == str(Path(tmpdir).resolve())
            assert stats["debounce_seconds"] == 0.1
            assert stats["last_rebuild_time"] > 0

            watcher.stop()
