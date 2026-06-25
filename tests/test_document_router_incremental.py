"""Tests for multi-format incremental document routing."""

import hashlib
from pathlib import Path

from src.parsers import document_router as router_module
from src.parsers.base_parser import Document
from src.parsers.document_router import DocumentRouter


class FakePDFParser:
    def __init__(self, base_path: str = ""):
        self.base_path = Path(base_path).resolve()

    def parse_file(self, file_path: str) -> Document:
        path = Path(file_path).resolve()
        content = path.read_text(encoding="utf-8")
        return Document(
            title=path.stem,
            content=content,
            source_file=str(path),
            relative_path=str(path.relative_to(self.base_path)),
            folder="root",
            content_hash=hashlib.md5(content.encode()).hexdigest(),
        )

    def parse_directory(self, dir_path: str, exclude_dirs=None) -> list[Document]:
        return [self.parse_file(str(path)) for path in Path(dir_path).rglob("*.pdf")]


def test_document_router_incremental_detects_changed_non_markdown_file(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    pdf = vault / "report.pdf"
    pdf.write_text("new report content that is long enough", encoding="utf-8")

    monkeypatch.setitem(router_module.PARSER_MAP, ".pdf", FakePDFParser)

    router = DocumentRouter(str(vault))
    changed, deleted = router.parse_directory_incremental(
        {"report.pdf": "old-hash", "removed.pdf": "gone"}
    )

    assert [doc.relative_path for doc in changed] == ["report.pdf"]
    assert deleted == ["removed.pdf"]


def test_document_router_incremental_skips_unchanged_non_markdown_file(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    pdf = vault / "report.pdf"
    content = "same report content that is long enough"
    pdf.write_text(content, encoding="utf-8")

    monkeypatch.setitem(router_module.PARSER_MAP, ".pdf", FakePDFParser)

    router = DocumentRouter(str(vault))
    changed, deleted = router.parse_directory_incremental(
        {"report.pdf": hashlib.md5(content.encode()).hexdigest()}
    )

    assert changed == []
    assert deleted == []
