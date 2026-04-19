"""Obsidian 笔记解析器

处理 Obsidian 特有的格式：
- YAML frontmatter 提取（date, tags, source）
- [[]] 双向链接解析
- # 标签提取
- 标题层级结构保留
- 增量解析（基于文件 MD5 检测变更）
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ObsidianNote:
    """解析后的 Obsidian 笔记"""
    title: str
    content: str          # 去除 frontmatter 后的正文
    raw_content: str      # 原始内容（含 frontmatter）
    source_file: str      # 文件路径
    relative_path: str    # 相对于 vault 根目录的路径
    folder: str           # 所在文件夹（用于领域分类）
    tags: list[str] = field(default_factory=list)
    date: Optional[str] = None
    outbound_links: list[str] = field(default_factory=list)  # 引用的其他笔记
    headings: list[str] = field(default_factory=list)         # 标题层级
    content_hash: str = ""  # 内容 MD5，用于增量检测


class ObsidianParser:
    """解析 Obsidian vault 中的 markdown 笔记"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()

    def parse_file(self, file_path: str) -> ObsidianNote:
        """解析单个 md 文件"""
        path = Path(file_path).resolve()
        raw = path.read_text(encoding="utf-8")
        rel_path = str(path.relative_to(self.vault_path))

        # 提取 frontmatter
        frontmatter, content = self._split_frontmatter(raw)

        # 解析 frontmatter
        tags = []
        date = None
        source = None
        if frontmatter:
            meta = yaml.safe_load(frontmatter) or {}
            tags = meta.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            date = meta.get("date")
            source = meta.get("source")

        # 标题：优先用文件名，否则取第一个 # 标题
        title = path.stem
        first_heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if first_heading:
            title = first_heading.group(1).strip()

        # 提取 [[]] 双向链接
        outbound_links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)

        # 提取标题层级
        headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        headings = [f"{'#' * int(len(h[0]))} {h[1].strip()}" for h in headings]

        # 文件夹（领域分类用）
        folder = str(path.parent.relative_to(self.vault_path)) if path.parent != self.vault_path else "root"

        # 内容哈希
        content_hash = hashlib.md5(content.encode()).hexdigest()

        return ObsidianNote(
            title=title,
            content=content.strip(),
            raw_content=raw,
            source_file=str(path),
            relative_path=rel_path,
            folder=folder,
            tags=tags,
            date=date,
            outbound_links=outbound_links,
            headings=headings,
            content_hash=content_hash,
        )

    def parse_vault(self, exclude_dirs: list[str] = None) -> list[ObsidianNote]:
        """递归解析整个 vault，返回所有笔记"""
        if exclude_dirs is None:
            exclude_dirs = [".obsidian", ".trash", ".git"]

        notes = []
        for md_file in self.vault_path.rglob("*.md"):
            if any(part in exclude_dirs for part in md_file.parts):
                continue
            try:
                note = self.parse_file(str(md_file))
                if len(note.content) > 10:
                    notes.append(note)
            except Exception as e:
                print(f"[WARN] 解析失败 {md_file}: {e}")

        return notes

    def parse_vault_incremental(
        self,
        manifest: dict[str, str],
        exclude_dirs: list[str] = None,
    ) -> tuple[list[ObsidianNote], list[str]]:
        """增量解析 vault，返回 (新增/变更笔记, 已删除文件相对路径列表)

        manifest: {relative_path: content_hash} 上次索引时的文件状态
        """
        if exclude_dirs is None:
            exclude_dirs = [".obsidian", ".trash", ".git"]

        current_files = {}
        for md_file in self.vault_path.rglob("*.md"):
            if any(part in exclude_dirs for part in md_file.parts):
                continue
            rel_path = str(md_file.relative_to(self.vault_path))
            current_files[rel_path] = md_file

        # 检测删除
        deleted = [rp for rp in manifest if rp not in current_files]

        # 检测新增和变更
        changed_notes = []
        for rel_path, md_file in current_files.items():
            old_hash = manifest.get(rel_path)
            if old_hash is None:
                # 新文件：需要解析
                pass
            else:
                # 快速检测：读取文件计算 MD5，不解析
                raw = md_file.read_text(encoding="utf-8")
                _, content = self._split_frontmatter(raw)
                current_hash = hashlib.md5(content.encode()).hexdigest()
                if current_hash == old_hash:
                    continue

            # 新增或变更：完整解析
            try:
                note = self.parse_file(str(md_file))
                if len(note.content) > 10:
                    changed_notes.append(note)
            except Exception as e:
                print(f"[WARN] 解析失败 {md_file}: {e}")

        return changed_notes, deleted

    def _split_frontmatter(self, raw: str) -> tuple[Optional[str], str]:
        """分离 YAML frontmatter 和正文"""
        if not raw.startswith("---"):
            return None, raw

        parts = raw.split("---", 2)
        if len(parts) < 3:
            return None, raw

        return parts[1].strip(), parts[2].strip()


# ---- 领域路由映射 ----

DOMAIN_MAP = {
    "得到笔记": "通识",
    "面试准备": "面试",
    "AI工程": "AI/ML",
    "Android": "编程",
    "Java": "编程",
}

def classify_domain(folder: str) -> str:
    """根据文件夹路径判断领域"""
    for key, domain in DOMAIN_MAP.items():
        if key in folder:
            return domain
    return "其他"


if __name__ == "__main__":
    # 测试解析
    vault = "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    parser = ObsidianParser(vault)

    # 解析单个文件
    sample = parser.parse_file(f"{vault}/得到笔记/20201009_一个国家想要维持安定团结的大一统局面，那有两件事情非做不可。第一件事情，....md")
    print(f"标题: {sample.title}")
    print(f"标签: {sample.tags}")
    print(f"日期: {sample.date}")
    print(f"领域: {classify_domain(sample.folder)}")
    print(f"链接: {sample.outbound_links[:3]}...")
    print(f"内容前100字: {sample.content[:100]}...")
