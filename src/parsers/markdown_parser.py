"""通用 Markdown 解析器"""

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from src.parsers.base_parser import BaseParser, Document


class MarkdownParser(BaseParser):
    """通用 Markdown 解析，无 Obsidian 特殊处理"""

    def __init__(self, base_path: str = ""):
        self.base_path = Path(base_path).resolve() if base_path else Path.cwd()

    def parse_file(self, file_path: str) -> Document:
        path = Path(file_path).resolve()
        content = path.read_text(encoding="utf-8")

        # 标题：取第一个 # 或文件名
        title = path.stem
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()

        rel_path = str(path.relative_to(self.base_path)) if path.is_relative_to(self.base_path) else path.name
        folder = str(path.parent.relative_to(self.base_path)) if path.parent != self.base_path else "root"

        return Document(
            title=title,
            content=content.strip(),
            source_file=str(path),
            relative_path=rel_path,
            folder=folder,
            content_hash=self.compute_hash(content),
        )

    def parse_directory(self, dir_path: str, exclude_dirs: list[str] = None) -> list[Document]:
        if exclude_dirs is None:
            exclude_dirs = [".git", ".obsidian", ".trash"]

        docs = []
        for md_file in Path(dir_path).rglob("*.md"):
            if any(part in exclude_dirs for part in md_file.parts):
                continue
            try:
                doc = self.parse_file(str(md_file))
                if len(doc.content) > 10:
                    docs.append(doc)
            except Exception as e:
                print(f"[WARN] 解析失败 {md_file}: {e}")

        return docs
