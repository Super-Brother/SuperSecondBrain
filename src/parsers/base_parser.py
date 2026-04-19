"""解析器抽象接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """统一的文档结构"""
    title: str
    content: str
    source_file: str
    relative_path: str
    folder: str
    tags: list[str] = field(default_factory=list)
    date: Optional[str] = None
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """解析器基类"""

    @abstractmethod
    def parse_file(self, file_path: str) -> Document:
        """解析单个文件"""
        pass

    @abstractmethod
    def parse_directory(self, dir_path: str, exclude_dirs: list[str] = None) -> list[Document]:
        """解析目录下所有支持的文件"""
        pass

    @staticmethod
    def compute_hash(content: str) -> str:
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()
