"""笔记管理模块 — 封装 vault 文件系统操作与索引同步

提供笔记级别的 CRUD：
- 列出、查看、搜索笔记
- 新建、编辑 Markdown 笔记
- 删除笔记
- 浏览文件夹和标签
"""

import re
from pathlib import Path

import yaml
from fastapi import HTTPException

from src.parsers.document_router import DocumentRouter
from src.parsers.obsidian_parser import ObsidianParser, classify_domain
from src.utils.logger import log


# ---- 辅助函数 ----


def _format_date(value) -> str | None:
    """将 YAML 解析出的 date 对象统一转为字符串"""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---- 安全工具 ----


def safe_path(vault_path: str, relative_path: str) -> Path:
    """安全解析相对路径，防止目录遍历攻击

    Args:
        vault_path: vault 根目录绝对路径
        relative_path: 用户传入的相对路径（URL decoded）

    Returns:
        解析后的绝对路径（已 resolve）

    Raises:
        HTTPException(400): 路径非法（含 ..、为空、不在 vault 内等）
    """
    if not relative_path or relative_path.strip() == "":
        raise HTTPException(status_code=400, detail="路径不能为空")

    # 拒绝任何包含 .. 的路径
    if ".." in relative_path.replace("\\", "/").split("/"):
        raise HTTPException(status_code=400, detail="非法路径：禁止目录遍历")

    vault = Path(vault_path).resolve()
    target = (vault / relative_path).resolve()

    # 确保目标路径在 vault 目录内
    try:
        target.relative_to(vault)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法路径：超出 vault 范围")

    return target


# ---- 解析工具 ----


def _parse_md_meta(parser: ObsidianParser, file_path: Path, rel_path: str, vault_path: str) -> dict | None:
    """解析 Markdown 文件元数据，失败时返回 None"""
    try:
        note = parser.parse_file(str(file_path))
        folder = str(file_path.parent.relative_to(Path(vault_path).resolve())) if file_path.parent != Path(vault_path) else "root"
        return {
            "title": note.title,
            "relative_path": rel_path,
            "folder": folder,
            "domain": classify_domain(folder),
            "tags": note.tags,
            "date": _format_date(note.date),
            "content_hash": note.content_hash,
            "outbound_links": note.outbound_links,
            "headings": note.headings,
            "format": "markdown",
        }
    except Exception:
        return None


def _parse_generic_meta(router: DocumentRouter, file_path: Path, rel_path: str, vault_path: str) -> dict:
    """解析非 Markdown 文件元数据，失败时回退到基本信息"""
    folder = str(file_path.parent.relative_to(Path(vault_path).resolve())) if file_path.parent != Path(vault_path) else "root"
    ext = file_path.suffix.lower().lstrip(".")
    try:
        doc = router.parse_file(str(file_path))
        return {
            "title": doc.title,
            "relative_path": rel_path,
            "folder": folder,
            "domain": classify_domain(folder),
            "tags": doc.tags,
            "date": _format_date(doc.date),
            "content_hash": doc.content_hash,
            "outbound_links": [],
            "headings": [],
            "format": ext,
        }
    except Exception:
        return {
            "title": file_path.stem,
            "relative_path": rel_path,
            "folder": folder,
            "domain": classify_domain(folder),
            "tags": [],
            "date": None,
            "content_hash": "",
            "outbound_links": [],
            "headings": [],
            "format": ext,
        }


# ---- 核心 CRUD ----


def list_notes(
    vault_path: str,
    page: int = 1,
    page_size: int = 20,
    folder: str | None = None,
    domain: str | None = None,
    tag: str | None = None,
    keyword: str | None = None,
) -> dict:
    """扫描 vault 文件系统，返回分页笔记列表

    支持按文件夹、领域、标签、关键词过滤。
    """
    vault = Path(vault_path).resolve()
    if not vault.exists():
        return {"total": 0, "page": page, "page_size": page_size, "items": []}

    parser = ObsidianParser(vault_path)
    router = DocumentRouter(use_obsidian=True)
    notes = []

    # 扫描所有支持的文件格式
    for ext in (".md", ".pdf", ".docx", ".pptx", ".xlsx"):
        for file_path in vault.rglob(f"*{ext}"):
            # 排除隐藏目录（.obsidian, .git 等）
            rel_parts = file_path.relative_to(vault).parts
            if any(part.startswith(".") for part in rel_parts):
                continue

            rel_path = str(file_path.relative_to(vault))
            meta = None
            if ext == ".md":
                meta = _parse_md_meta(parser, file_path, rel_path, vault_path)
            if meta is None:
                meta = _parse_generic_meta(router, file_path, rel_path, vault_path)
            notes.append(meta)

    # ---- 过滤 ----
    if folder:
        notes = [n for n in notes if n["folder"] == folder or n["folder"].startswith(folder + "/")]
    if domain:
        notes = [n for n in notes if n.get("domain") == domain]
    if tag:
        notes = [n for n in notes if tag in n.get("tags", [])]
    if keyword:
        kw = keyword.lower()
        notes = [n for n in notes if kw in n["title"].lower()]

    # 排序：按文件夹+标题
    notes.sort(key=lambda n: (n["folder"], n["title"]))

    total = len(notes)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": notes[start:end],
    }


def get_note(vault_path: str, relative_path: str) -> dict:
    """获取单个笔记详情

    Markdown 返回完整内容（含 raw_content 供编辑）；
    其他格式返回元数据 + is_downloadable=True。
    """
    file_path = safe_path(vault_path, relative_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="笔记不存在")

    ext = file_path.suffix.lower()
    folder = str(file_path.parent.relative_to(Path(vault_path).resolve())) if file_path.parent != Path(vault_path) else "root"

    if ext == ".md":
        parser = ObsidianParser(vault_path)
        note = parser.parse_file(str(file_path))
        return {
            "title": note.title,
            "relative_path": relative_path,
            "folder": folder,
            "domain": classify_domain(folder),
            "tags": note.tags,
            "date": _format_date(note.date),
            "content_hash": note.content_hash,
            "outbound_links": note.outbound_links,
            "headings": note.headings,
            "format": "markdown",
            "content": note.content,
            "raw_content": note.raw_content,
            "word_count": len(note.content),
            "is_downloadable": False,
        }

    # 非 Markdown：返回元数据 + 下载标志
    router = DocumentRouter(use_obsidian=True)
    try:
        doc = router.parse_file(str(file_path))
        title = doc.title
        tags = doc.tags
        date = doc.date
        content_hash = doc.content_hash
    except Exception:
        title = file_path.stem
        tags = []
        date = None
        content_hash = ""

    return {
        "title": title,
        "relative_path": relative_path,
        "folder": folder,
        "domain": classify_domain(folder),
        "tags": tags,
        "date": _format_date(date),
        "content_hash": content_hash,
        "outbound_links": [],
        "headings": [],
        "format": ext.lstrip("."),
        "content": "",
        "raw_content": "",
        "word_count": 0,
        "is_downloadable": True,
    }


def create_note(
    vault_path: str,
    relative_path: str,
    title: str,
    content: str = "",
    tags: list[str] | None = None,
    date: str | None = None,
    frontmatter: dict | None = None,
) -> dict:
    """新建 Markdown 笔记

    根据参数构建 frontmatter + Markdown 正文，写入 vault 文件系统。
    """
    file_path = safe_path(vault_path, relative_path)

    if file_path.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="只允许创建 Markdown（.md）笔记")
    if file_path.exists():
        raise HTTPException(status_code=409, detail="笔记已存在")

    # 构建 frontmatter
    fm = dict(frontmatter or {})
    if tags:
        fm["tags"] = tags
    if date:
        fm["date"] = date

    # 构建文件内容
    lines = []
    if fm:
        lines.append("---")
        lines.append(yaml.dump(fm, allow_unicode=True, sort_keys=False).strip())
        lines.append("---")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(content)

    # 确保父目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("\n".join(lines), encoding="utf-8")

    return get_note(vault_path, relative_path)


def update_note(
    vault_path: str,
    relative_path: str,
    content: str | None = None,
    tags: list[str] | None = None,
    date: str | None = None,
    frontmatter: dict | None = None,
) -> dict:
    """更新 Markdown 笔记

    读取现有 frontmatter，与用户传入的字段合并，重新写入文件。
    """
    file_path = safe_path(vault_path, relative_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="笔记不存在")
    if file_path.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="只允许编辑 Markdown（.md）笔记")

    raw = file_path.read_text(encoding="utf-8")

    # 解析现有 frontmatter 和正文
    existing_fm = {}
    existing_title = file_path.stem
    existing_content = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                existing_fm = yaml.safe_load(parts[1]) or {}
                remaining = parts[2].strip()
                title_match = re.search(r"^#\s+(.+)$", remaining, re.MULTILINE)
                if title_match:
                    existing_title = title_match.group(1).strip()
                    existing_content = re.sub(r"^#\s+.+\n*", "", remaining, count=1).strip()
                else:
                    existing_content = remaining
            except Exception:
                pass

    # 合并 frontmatter
    new_fm = dict(existing_fm)
    if frontmatter is not None:
        new_fm.update(frontmatter)
    if tags is not None:
        if tags:
            new_fm["tags"] = tags
        elif "tags" in new_fm:
            del new_fm["tags"]
    if date is not None:
        if date:
            new_fm["date"] = date
        elif "date" in new_fm:
            del new_fm["date"]

    # 合并正文
    new_content = content if content is not None else existing_content

    # 重建文件
    lines = []
    if new_fm:
        lines.append("---")
        lines.append(yaml.dump(new_fm, allow_unicode=True, sort_keys=False).strip())
        lines.append("---")
    lines.append(f"# {existing_title}")
    lines.append("")
    lines.append(new_content)

    file_path.write_text("\n".join(lines), encoding="utf-8")

    return get_note(vault_path, relative_path)


def delete_note(vault_path: str, relative_path: str) -> bool:
    """删除笔记文件"""
    file_path = safe_path(vault_path, relative_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="笔记不存在")

    file_path.unlink()
    return True


# ---- 搜索 ----


def search_notes(pipeline_obj, query: str, top_k: int = 20, domain_filter: str | None = None) -> list[dict]:
    """通过 RAG 检索器搜索笔记

    调用 pipeline.rag_retriever.retrieve() 获取 chunks，
    按 relative_path 聚合为笔记级别的结果。
    """
    if pipeline_obj is None or pipeline_obj.rag_retriever is None:
        raise HTTPException(status_code=503, detail="检索服务未就绪")

    from src.retrievers.rag_retriever import SearchConfig

    config = SearchConfig(
        top_k=top_k,
        rerank_top_k=min(top_k, 10),
        domain_filter=domain_filter,
    )
    results = pipeline_obj.rag_retriever.retrieve(query, config)

    # 按 relative_path 聚合
    seen: dict[str, dict] = {}
    for doc, score in results:
        rp = doc.metadata.get("relative_path", "")
        if not rp or rp in seen:
            if rp in seen:
                # 追加匹配片段
                chunk_text = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
                if chunk_text not in seen[rp]["matched_chunks"]:
                    seen[rp]["matched_chunks"].append(chunk_text)
            continue

        chunk_text = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
        seen[rp] = {
            "score": round(float(score), 4),
            "note": {
                "title": doc.metadata.get("title", ""),
                "relative_path": rp,
                "folder": doc.metadata.get("folder", ""),
                "domain": doc.metadata.get("domain", ""),
                "tags": doc.metadata.get("tags", []),
                "date": _format_date(doc.metadata.get("date")),
                "content_hash": doc.metadata.get("content_hash", ""),
                "outbound_links": doc.metadata.get("outbound_links", []),
                "headings": [],
                "format": "markdown" if rp.endswith(".md") else rp.split(".")[-1],
            },
            "matched_chunks": [chunk_text],
        }

    return list(seen.values())


# ---- 浏览 ----


def list_folders(vault_path: str) -> list[str]:
    """列出 vault 中所有包含文档的文件夹"""
    vault = Path(vault_path).resolve()
    if not vault.exists():
        return []

    folders = set()
    for ext in (".md", ".pdf", ".docx", ".pptx", ".xlsx"):
        for file_path in vault.rglob(f"*{ext}"):
            rel_parts = file_path.relative_to(vault).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            rel = file_path.relative_to(vault)
            parent = str(rel.parent) if rel.parent != Path(".") else "root"
            folders.add(parent)

    return sorted(folders)


def list_tags(vault_path: str) -> list[dict]:
    """扫描所有 Markdown 笔记，收集全局标签及使用次数"""
    vault = Path(vault_path).resolve()
    if not vault.exists():
        return []

    tag_counts: dict[str, int] = {}
    parser = ObsidianParser(vault_path)

    for md_file in vault.rglob("*.md"):
        rel_parts = md_file.relative_to(vault).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            note = parser.parse_file(str(md_file))
            for tag in note.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except Exception:
            pass

    return [{"name": k, "count": v} for k, v in sorted(tag_counts.items(), key=lambda x: -x[1])]
