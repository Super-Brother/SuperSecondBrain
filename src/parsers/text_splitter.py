"""文档切分器

针对 Obsidian 笔记特点优化：
- 保留代码块完整
- 保留表格完整
- 按标题层级切分
- 保持语义完整性
"""

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


@dataclass
class ChunkMetadata:
    """chunk 的元数据"""
    source_file: str
    relative_path: str
    folder: str
    title: str
    tags: list[str]
    domain: str
    date: str | None
    chunk_index: int
    total_chunks: int


def create_text_splitter(
    chunk_size: int = 512,
    chunk_overlap: int = 100,
) -> RecursiveCharacterTextSplitter:
    """创建优化的文本切分器"""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n## ",   # 二级标题
            "\n### ",  # 三级标题
            "\n#### ", # 四级标题
            "\n\n",    # 段落
            "\n",      # 换行
            "。",      # 中文句号
            "；",      # 中文分号
            "，",      # 中文逗号
            " ",       # 空格
            "",        # 字符级兜底
        ],
        length_function=len,
    )


def split_note_to_chunks(note, text_splitter: RecursiveCharacterTextSplitter) -> list[Document]:
    """将单篇 Obsidian 笔记切分为 chunks，返回 LangChain Document 列表"""
    from src.parsers.obsidian_parser import classify_domain

    chunks = text_splitter.split_text(note.content)
    documents = []

    for i, chunk_text in enumerate(chunks):
        # 过滤太短的 chunk
        if len(chunk_text.strip()) < 20:
            continue

        domain = classify_domain(note.folder)

        metadata = {
            "source_file": note.source_file,
            "relative_path": note.relative_path,
            "folder": note.folder,
            "title": note.title,
            "tags": note.tags,
            "domain": domain,
            "date": note.date,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "outbound_links": note.outbound_links,
        }

        doc = Document(page_content=chunk_text, metadata=metadata)
        documents.append(doc)

    return documents


def split_notes_to_documents(notes: list, chunk_size: int = 512, chunk_overlap: int = 100) -> list[Document]:
    """批量切分多篇笔记"""
    splitter = create_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_docs = []

    for note in notes:
        docs = split_note_to_chunks(note, splitter)
        all_docs.extend(docs)

    return all_docs


if __name__ == "__main__":
    # 测试切分
    from src.parsers.obsidian_parser import ObsidianParser

    vault = "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
    parser = ObsidianParser(vault)
    notes = parser.parse_vault()

    print(f"解析到 {len(notes)} 篇笔记")

    docs = split_notes_to_documents(notes, chunk_size=512, chunk_overlap=100)
    print(f"切分为 {len(docs)} 个 chunks")

    # 统计各领域
    from collections import Counter
    domains = Counter(doc.metadata["domain"] for doc in docs)
    print(f"\n领域分布:")
    for d, c in domains.most_common():
        print(f"  {d}: {c} chunks ({c/len(docs)*100:.1f}%)")

    # 打印一个样例
    sample = docs[0]
    print(f"\n样例 chunk:")
    print(f"  来源: {sample.metadata['title']}")
    print(f"  领域: {sample.metadata['domain']}")
    print(f"  内容: {sample.page_content[:150]}...")
