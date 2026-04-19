"""PDF 解析器"""

import hashlib
import os
import re
from pathlib import Path

from src.parsers.base_parser import BaseParser, Document


class PDFParser(BaseParser):
    """PDF 解析，依赖 PyMuPDF"""

    def __init__(self, base_path: str = ""):
        self.base_path = Path(base_path).resolve() if base_path else Path.cwd()
        self._fitz = None

    @property
    def fitz(self):
        if self._fitz is None:
            import fitz
            self._fitz = fitz
        return self._fitz

    def parse_file(self, file_path: str) -> Document:
        path = Path(file_path).resolve()
        doc = self.fitz.open(str(path))

        # 提取所有页面文本
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())

        content = "\n\n---PAGE---\n\n".join(pages)
        title = path.stem

        # 尝试从 PDF 元数据获取标题
        meta = doc.metadata
        if meta and meta.get("title"):
            title = meta["title"]

        rel_path = str(path.relative_to(self.base_path)) if path.is_relative_to(self.base_path) else path.name
        folder = str(path.parent.relative_to(self.base_path)) if path.parent != self.base_path else "root"

        doc.close()

        return Document(
            title=title,
            content=content,
            source_file=str(path),
            relative_path=rel_path,
            folder=folder,
            content_hash=self.compute_hash(content),
            metadata={"page_count": len(pages)},
        )

    def parse_directory(self, dir_path: str, exclude_dirs: list[str] = None) -> list[Document]:
        if exclude_dirs is None:
            exclude_dirs = [".git"]

        docs = []
        for pdf_file in Path(dir_path).rglob("*.pdf"):
            if any(part in exclude_dirs for part in pdf_file.parts):
                continue
            try:
                doc = self.parse_file(str(pdf_file))
                if len(doc.content) > 50:
                    docs.append(doc)
            except Exception as e:
                print(f"[WARN] PDF解析失败 {pdf_file}: {e}")

        return docs
