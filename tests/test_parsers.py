"""测试 Obsidian 解析器"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parsers.base_parser import Document
from src.parsers.obsidian_parser import ObsidianParser, ObsidianNote, classify_domain, DOMAIN_MAP
from src.parsers.document_router import DocumentRouter


def _write_note(tmpdir: str, rel_path: str, content: str):
    fp = Path(tmpdir) / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return str(fp)


class TestObsidianParser:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.parser = ObsidianParser(self.tmpdir)

    def test_parse_plain_note(self):
        fp = _write_note(self.tmpdir, "test.md", "# 标题\n正文内容")
        note = self.parser.parse_file(fp)
        assert note.title == "标题"
        assert "正文内容" in note.content
        assert note.folder == "root"

    def test_parse_frontmatter(self):
        content = "---\ntags: [a, b]\ndate: 2024-01-01\n---\n正文"
        fp = _write_note(self.tmpdir, "note.md", content)
        note = self.parser.parse_file(fp)
        assert note.tags == ["a", "b"]
        assert str(note.date) == "2024-01-01"

    def test_parse_frontmatter_string_tag(self):
        content = "---\ntags: single\n---\n正文"
        fp = _write_note(self.tmpdir, "note.md", content)
        note = self.parser.parse_file(fp)
        assert note.tags == ["single"]

    def test_parse_wikilinks(self):
        content = "链接 [[目标笔记]] 和 [[带别名|显示文本]]"
        fp = _write_note(self.tmpdir, "note.md", content)
        note = self.parser.parse_file(fp)
        assert "目标笔记" in note.outbound_links
        assert "带别名" in note.outbound_links

    def test_parse_headings(self):
        content = "# H1\n## H2\n### H3"
        fp = _write_note(self.tmpdir, "note.md", content)
        note = self.parser.parse_file(fp)
        assert len(note.headings) == 3

    def test_parse_vault_excludes_dirs(self):
        _write_note(self.tmpdir, "good.md", "有足够长度的内容" * 5)
        _write_note(self.tmpdir, ".obsidian/config.md", "忽略我")
        notes = self.parser.parse_vault()
        assert len(notes) == 1

    def test_parse_vault_skips_short_notes(self):
        _write_note(self.tmpdir, "short.md", "短")
        _write_note(self.tmpdir, "long.md", "这是一篇足够长的笔记内容" * 5)
        notes = self.parser.parse_vault()
        assert len(notes) == 1

    def test_content_hash(self):
        _write_note(self.tmpdir, "a.md", "# T\n内容一致" * 10)
        _write_note(self.tmpdir, "b.md", "# T\n内容一致" * 10)
        notes = self.parser.parse_vault()
        assert notes[0].content_hash == notes[1].content_hash

    def test_folder_detection(self):
        _write_note(self.tmpdir, "子目录/note.md", "# T\n" + "内容" * 10)
        notes = self.parser.parse_vault()
        assert notes[0].folder == "子目录"


class TestClassifyDomain:
    def test_known_domains(self):
        assert classify_domain("得到笔记/xxx") == "通识"
        assert classify_domain("AI工程/xxx") == "AI/ML"
        assert classify_domain("Java/xxx") == "编程"
        assert classify_domain("面试准备/xxx") == "面试"

    def test_unknown_domain(self):
        assert classify_domain("随便什么") == "其他"


class TestIncrementalParse:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.parser = ObsidianParser(self.tmpdir)

    def test_detect_new_file(self):
        manifest = {}
        _write_note(self.tmpdir, "new.md", "# T\n" + "内容" * 10)
        changed, deleted = self.parser.parse_vault_incremental(manifest)
        assert len(changed) == 1
        assert len(deleted) == 0

    def test_detect_deleted(self):
        _write_note(self.tmpdir, "old.md", "# T\n" + "内容" * 10)
        notes = self.parser.parse_vault()
        manifest = {n.relative_path: n.content_hash for n in notes}
        # 删除文件后检测
        os.remove(Path(self.tmpdir) / "old.md")
        changed, deleted = self.parser.parse_vault_incremental(manifest)
        assert len(changed) == 0
        assert len(deleted) == 1

    def test_detect_modified(self):
        fp = _write_note(self.tmpdir, "note.md", "# T\n" + "旧内容" * 10)
        notes = self.parser.parse_vault()
        manifest = {n.relative_path: n.content_hash for n in notes}
        # 修改文件
        Path(fp).write_text("# T\n" + "新内容" * 10, encoding="utf-8")
        changed, deleted = self.parser.parse_vault_incremental(manifest)
        assert len(changed) == 1

    def test_no_changes(self):
        _write_note(self.tmpdir, "note.md", "# T\n" + "内容" * 10)
        notes = self.parser.parse_vault()
        manifest = {n.relative_path: n.content_hash for n in notes}
        changed, deleted = self.parser.parse_vault_incremental(manifest)
        assert len(changed) == 0
        assert len(deleted) == 0


class TestDocumentRouterObsidianMixedFormats:
    def test_obsidian_vault_keeps_parsing_non_markdown_formats(self, tmp_path):
        (tmp_path / ".obsidian").mkdir()
        md_file = tmp_path / "note.md"
        pdf_file = tmp_path / "uploads" / "manual.pdf"
        pdf_file.parent.mkdir()
        md_file.write_text("# 标题\n" + "正文内容" * 10, encoding="utf-8")
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        obs_note = ObsidianNote(
            title="标题",
            content="正文内容" * 10,
            raw_content="# 标题\n" + "正文内容" * 10,
            source_file=str(md_file),
            relative_path="note.md",
            folder="root",
            outbound_links=["另一篇笔记"],
            content_hash="hash",
        )

        pdf_doc = MagicMock()
        pdf_doc.metadata = {"source_file": str(pdf_file), "format": "pdf"}

        router = DocumentRouter(str(tmp_path), use_obsidian=True)

        with patch("src.parsers.document_router.ObsidianParser") as obs_cls:
            obs_cls.return_value.parse_vault.return_value = [obs_note]

            with patch.object(router, "_get_parser", return_value=None) as mock_get:
                def side_effect(ext):
                    if ext == ".pdf":
                        mock_pdf = MagicMock()
                        mock_pdf.parse_directory.return_value = [pdf_doc]
                        return mock_pdf
                    return None
                mock_get.side_effect = side_effect

                docs = router.parse_directory(str(tmp_path))

        assert len(docs) == 2
        assert isinstance(docs[0], Document)
        assert docs[0].relative_path == "note.md"
        assert docs[0].metadata["outbound_links"] == ["另一篇笔记"]
        assert docs[1] is pdf_doc
        obs_cls.return_value.parse_vault.assert_called_once()
        mock_get.assert_any_call(".pdf")
