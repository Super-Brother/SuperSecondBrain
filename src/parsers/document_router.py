"""文档路由器 — 根据文件扩展名自动路由到对应解析器"""

from pathlib import Path
from typing import Type

from src.parsers.base_parser import BaseParser, Document
from src.parsers.markdown_parser import MarkdownParser
from src.parsers.pdf_parser import PDFParser
from src.parsers.office_parser import WordParser, PPTParser, ExcelParser
from src.parsers.obsidian_parser import ObsidianParser


# 扩展名 → 解析器类
PARSER_MAP: dict[str, Type[BaseParser]] = {
    ".md": MarkdownParser,
    ".pdf": PDFParser,
    ".docx": WordParser,
    ".pptx": PPTParser,
    ".xlsx": ExcelParser,
}

# Obsidian vault 专用
OBSIDIAN_EXTENSIONS = {".md"}


class DocumentRouter:
    """根据文件类型自动路由解析器"""

    def __init__(self, base_path: str = "", use_obsidian: bool = False):
        self.base_path = Path(base_path).resolve() if base_path else Path.cwd()
        self.use_obsidian = use_obsidian
        self._parsers: dict[str, BaseParser] = {}

    def _get_parser(self, ext: str) -> BaseParser | None:
        if ext not in PARSER_MAP:
            return None

        if ext not in self._parsers:
            parser_cls = PARSER_MAP[ext]
            self._parsers[ext] = parser_cls(str(self.base_path))

        return self._parsers[ext]

    def parse_file(self, file_path: str) -> Document | None:
        path = Path(file_path)
        ext = path.suffix.lower()

        parser = self._get_parser(ext)
        if parser is None:
            return None

        return parser.parse_file(file_path)

    def parse_directory(
        self,
        dir_path: str,
        include_types: list[str] | None = None,
        exclude_dirs: list[str] | None = None,
    ) -> list[Document]:
        if exclude_dirs is None:
            exclude_dirs = [".git", ".obsidian", ".trash", "__pycache__"]

        target_path = Path(dir_path)
        all_docs = []

        parsed_obsidian_markdown = False
        if self.use_obsidian and (target_path / ".obsidian").exists():
            obs_parser = ObsidianParser(str(target_path))
            for note in obs_parser.parse_vault():
                all_docs.append(
                    Document(
                        title=note.title,
                        content=note.content,
                        source_file=note.source_file,
                        relative_path=note.relative_path,
                        folder=note.folder,
                        tags=note.tags,
                        date=note.date,
                        content_hash=note.content_hash,
                        metadata={
                            "outbound_links": note.outbound_links,
                            "headings": note.headings,
                        },
                    )
                )
            parsed_obsidian_markdown = True

        for ext in PARSER_MAP:
            if parsed_obsidian_markdown and ext in OBSIDIAN_EXTENSIONS:
                continue
            if include_types and ext not in include_types:
                continue

            parser = self._get_parser(ext)
            if parser is None:
                continue

            docs = parser.parse_directory(dir_path, exclude_dirs=exclude_dirs)
            all_docs.extend(docs)

        return all_docs

    def parse_directory_incremental(
        self,
        manifest: dict[str, str],
        dir_path: str | None = None,
        include_types: list[str] | None = None,
        exclude_dirs: list[str] | None = None,
    ) -> tuple[list[Document], list[str]]:
        """Parse only new/changed supported files and report deleted paths."""
        if exclude_dirs is None:
            exclude_dirs = [".git", ".obsidian", ".trash", "__pycache__"]

        target_path = Path(dir_path).resolve() if dir_path else self.base_path
        include_set = {ext.lower() for ext in include_types} if include_types else None

        current_files: dict[str, Path] = {}
        for path in target_path.rglob("*"):
            if path.is_dir():
                continue
            if any(part in exclude_dirs for part in path.parts):
                continue
            ext = path.suffix.lower()
            if ext not in PARSER_MAP:
                continue
            if include_set is not None and ext not in include_set:
                continue
            try:
                rel_path = str(path.resolve().relative_to(self.base_path))
            except ValueError:
                rel_path = path.name
            current_files[rel_path] = path

        deleted = []
        for rel_path in manifest:
            ext = Path(rel_path).suffix.lower()
            if ext not in PARSER_MAP:
                continue
            if include_set is not None and ext not in include_set:
                continue
            if rel_path not in current_files:
                deleted.append(rel_path)

        changed_docs: list[Document] = []
        obs_parser = None
        if self.use_obsidian and (target_path / ".obsidian").exists():
            obs_parser = ObsidianParser(str(target_path))

        for rel_path, path in current_files.items():
            try:
                if obs_parser is not None and path.suffix.lower() in OBSIDIAN_EXTENSIONS:
                    note = obs_parser.parse_file(str(path))
                    doc = Document(
                        title=note.title,
                        content=note.content,
                        source_file=note.source_file,
                        relative_path=note.relative_path,
                        folder=note.folder,
                        tags=note.tags,
                        date=note.date,
                        content_hash=note.content_hash,
                        metadata={
                            "outbound_links": note.outbound_links,
                            "headings": note.headings,
                        },
                    )
                else:
                    parsed = self.parse_file(str(path))
                    if parsed is None:
                        continue
                    doc = parsed

                if len(doc.content) <= 10:
                    continue
                if manifest.get(rel_path) == doc.content_hash:
                    continue
                changed_docs.append(doc)
            except Exception as e:
                print(f"[WARN] 解析失败 {path}: {e}")

        return changed_docs, deleted
