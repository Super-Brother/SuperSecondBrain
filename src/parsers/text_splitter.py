"""文档切分器 — 六维优化：结构感知 + Token级 + 语义边界 + 层次切分 + 自适应 + 上下文

使用方式：
    from src.parsers.text_splitter import create_text_splitter, split_notes_to_documents

    splitter = create_text_splitter(strategy="markdown")  # markdown | semantic | legacy
    docs = split_notes_to_documents(notes, splitter=splitter)
"""

import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
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


# ---- 常量 ----

DOMAIN_CHUNK_SIZES = {
    "code": 256,
    "technical": 256,
    "general": 512,
    "prose": 1024,
}

CODE_KEYWORDS = {
    "def ", "class ", "import ", "function", "const ", "let ", "var ",
    "return ", "if ", "for ", "while ", "export ", "async ", "await ",
}

# ---- 正则：预提取 Markdown 原子单元 ----

CODE_BLOCK_RE = re.compile(r"```[\w]*\n[\s\S]*?\n```", re.MULTILINE)
TABLE_RE = re.compile(r"(?:^\|.*\|\n?)+", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
MAJOR_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)

# ---- Tokenizer 延迟加载 ----

_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-zh-v1.5")
    return _tokenizer


def _token_len(text: str) -> int:
    """按 Token 计数（BGE tokenizer）"""
    return len(_get_tokenizer().encode(text, add_special_tokens=False))


# ---- Embedding 缓存 ----

class EmbeddingCache:
    """句子级 Embedding，支持单 call 内去重缓存。"""

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._call_cache: dict[str, np.ndarray] = {}

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, sentences: list[str]) -> np.ndarray:
        """编码句子，自动去重并缓存。"""
        if not sentences:
            return np.array([])

        # 去重，保留顺序映射
        unique_sents: list[str] = []
        sent_to_idx: dict[str, int] = {}
        order_map: list[int] = []

        for s in sentences:
            key = s.strip()
            if key not in sent_to_idx:
                sent_to_idx[key] = len(unique_sents)
                unique_sents.append(key)
            order_map.append(sent_to_idx[key])

        # 分离已缓存和待编码
        cached: dict[int, np.ndarray] = {}
        to_encode: list[str] = []
        encode_indices: list[int] = []

        for i, s in enumerate(unique_sents):
            if s in self._call_cache:
                cached[i] = self._call_cache[s]
            else:
                to_encode.append(s)
                encode_indices.append(i)

        if to_encode:
            embeddings = self.model.encode(to_encode, normalize_embeddings=True)
            for unique_idx, emb in zip(encode_indices, embeddings):
                self._call_cache[unique_sents[unique_idx]] = emb
                cached[unique_idx] = emb

        # 按原始顺序重组
        result = np.array([cached[order_map[i]] for i in range(len(sentences))])
        return result

    def clear_call_cache(self):
        self._call_cache.clear()


_embedder = EmbeddingCache()


# ---- 结构感知：提取原子单元 ----


def _extract_atomic_units(text: str) -> list[tuple[str, str]]:
    """
    将文本拆分为原子单元列表。
    每个元素为 (type, content)，type 可选：code_block, table, heading, text
    """
    units = []
    last_end = 0

    # 先提取代码块
    for m in CODE_BLOCK_RE.finditer(text):
        if m.start() > last_end:
            units.extend(_split_plain_text(text[last_end : m.start()]))
        units.append(("code_block", m.group()))
        last_end = m.end()

    remaining = text[last_end:]
    if remaining:
        units.extend(_split_plain_text(remaining))

    return units


def _split_plain_text(text: str) -> list[tuple[str, str]]:
    """对纯文本部分，按表格、标题、段落进一步拆分"""
    units = []
    last_end = 0

    # 提取表格
    for m in TABLE_RE.finditer(text):
        if m.start() > last_end:
            units.extend(_split_by_headings(text[last_end : m.start()]))
        units.append(("table", m.group()))
        last_end = m.end()

    remaining = text[last_end:]
    if remaining:
        units.extend(_split_by_headings(remaining))

    return units


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """按标题切分文本"""
    units = []
    last_end = 0

    for m in HEADING_RE.finditer(text):
        if m.start() > last_end:
            chunk = text[last_end : m.start()].strip()
            if chunk:
                units.append(("text", chunk))
        units.append(("heading", m.group().strip()))
        last_end = m.end()

    remaining = text[last_end:].strip()
    if remaining:
        units.append(("text", remaining))

    return units


# ---- 层次切分：按大标题拆分 ----


def _split_by_major_headings(text: str) -> list[tuple[str, str, list[str]]]:
    """
    按 h1/h2 拆分为 section。
    返回 [(section_text, current_heading, heading_stack), ...]
    heading_stack 记录当前 section 的完整标题路径。
    """
    sections = []
    last_end = 0
    current_heading = ""
    heading_stack: list[str] = []

    for m in MAJOR_HEADING_RE.finditer(text):
        if m.start() > last_end:
            section_text = text[last_end : m.start()].strip()
            if section_text:
                sections.append((section_text, current_heading, list(heading_stack)))

        level = len(m.group(1))
        title = m.group(2).strip()

        while len(heading_stack) >= level:
            heading_stack.pop()
        heading_stack.append(title)
        current_heading = title
        last_end = m.end()

    remaining = text[last_end:].strip()
    if remaining:
        sections.append((remaining, current_heading, list(heading_stack)))

    if not sections:
        return [(text, "", [])]

    return sections


# ---- 内容类型检测 ----


def _detect_content_type(text: str) -> str:
    """启发式检测内容类型，用于自适应 chunk_size。"""
    lines = text.split("\n")
    if not lines:
        return "general"

    code_lines = sum(1 for line in lines if any(kw in line for kw in CODE_KEYWORDS))
    code_ratio = code_lines / len(lines)
    if code_ratio > 0.3:
        return "code"

    technical_patterns = [r"`[^`]+`", r"\*\*[^*]+\*\*", r"\[.*?\]\(.*?\)"]
    technical_count = sum(len(re.findall(p, text)) for p in technical_patterns)
    if technical_count > len(lines) * 0.2:
        return "technical"

    sentences = [s for s in re.split(r"[。！？\n]", text) if s.strip()]
    avg_sent_len = len(text) / max(len(sentences), 1)
    if avg_sent_len > 50:
        return "prose"

    return "general"


# ---- 语义边界切分（滑动窗口） ----


def _semantic_split(
    text: str,
    chunk_size: int = 512,
    overlap: int = 100,
    similarity_threshold: float = 0.5,
    sliding_window_size: int = 3,
) -> list[str]:
    """
    语义边界切分：
    1. 按句子切分
    2. 计算句子 embeddings（去重缓存）
    3. 构建句子-句子相似度矩阵
    4. 滑动窗口计算 coherence score（左右窗口 cross-similarity）
    5. 在 token 接近上限时，检查 coherence 局部最小值或低于阈值，决定是否切分
    6. 构建语义感知的 overlap
    """
    sentences = re.split(r"([。；！？\n]+)", text)
    sentences = [
        sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
        for i in range(0, len(sentences), 2)
        if sentences[i].strip()
    ]

    if not sentences:
        return [text] if text.strip() else []
    if len(sentences) == 1:
        return [sentences[0]]

    embeddings = _embedder.encode(sentences)
    sim_matrix = embeddings @ embeddings.T

    # 滑动窗口 coherence
    window_coherence: list[float] = []
    for i in range(len(sentences)):
        left_window = list(range(max(0, i - sliding_window_size), i))
        right_window = list(range(i + 1, min(len(sentences), i + sliding_window_size + 1)))

        if not left_window or not right_window:
            window_coherence.append(1.0)
            continue

        cross_sims = sim_matrix[np.ix_(left_window, right_window)]
        window_coherence.append(float(cross_sims.mean()))

    chunks: list[str] = []
    current_chunk: list[str] = [sentences[0]]
    current_tokens = _token_len(sentences[0])

    for i in range(1, len(sentences)):
        sent = sentences[i]
        sent_tokens = _token_len(sent)
        hard_limit = int(chunk_size * 1.2)

        must_split = current_tokens + sent_tokens > hard_limit
        should_split = False

        if not must_split and current_tokens + sent_tokens > chunk_size:
            prev_coh = window_coherence[i - 1] if i > 0 else 1.0
            curr_coh = window_coherence[i]
            next_coh = window_coherence[i + 1] if i < len(window_coherence) - 1 else 1.0

            is_local_min = curr_coh < prev_coh and curr_coh < next_coh
            below_threshold = curr_coh < similarity_threshold
            should_split = is_local_min or below_threshold

        if must_split or should_split:
            chunks.append("".join(current_chunk))
            current_chunk = _build_overlap(current_chunk, overlap)
            current_chunk.append(sent)
            current_tokens = sum(_token_len(s) for s in current_chunk)
        else:
            current_chunk.append(sent)
            current_tokens += sent_tokens

    if current_chunk:
        chunks.append("".join(current_chunk))

    _embedder.clear_call_cache()
    return [c for c in chunks if c.strip()]


def _build_overlap(current_chunk: list[str], overlap_tokens: int) -> list[str]:
    """
    构建语义感知的 overlap。
    从 current_chunk 尾部逆向取句子，确保 overlap 区域语义自洽。
    """
    if not current_chunk:
        return []

    overlap_sentences: list[str] = []
    overlap_token_count = 0

    for sent in reversed(current_chunk):
        st = _token_len(sent)
        if overlap_token_count + st > overlap_tokens:
            break
        overlap_sentences.insert(0, sent)
        overlap_token_count += st

    if len(overlap_sentences) >= 2:
        overlap_emb = _embedder.encode(overlap_sentences)
        first_sim = float(overlap_emb[0] @ overlap_emb[1:].mean(axis=0))
        if first_sim < 0.3 and len(overlap_sentences) > 1:
            overlap_sentences = overlap_sentences[1:]

    return list(overlap_sentences)


# ---- Splitter 类 ----


class MarkdownAwareSplitter:
    """
    结构感知 + Token 级 + 语义边界 + 层次切分。
    先按 h1/h2 拆分为 section，再提取原子单元，最后语义切分。
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 100,
        similarity_threshold: float = 0.5,
        enable_hierarchical: bool = True,
        enable_adaptive_size: bool = False,
        enable_context_association: bool = True,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.similarity_threshold = similarity_threshold
        self.enable_hierarchical = enable_hierarchical
        self.enable_adaptive_size = enable_adaptive_size
        self.enable_context_association = enable_context_association

    def split_text(self, text: str) -> list[str]:
        if self.enable_hierarchical:
            return self._split_hierarchical(text)
        return self._split_flat(text)

    def _split_hierarchical(self, text: str) -> list[str]:
        sections = _split_by_major_headings(text)
        all_chunks: list[str] = []

        for section_text, _section_heading, heading_stack in sections:
            effective_size = self.chunk_size
            if self.enable_adaptive_size:
                content_type = _detect_content_type(section_text)
                effective_size = DOMAIN_CHUNK_SIZES.get(content_type, self.chunk_size)

            units = _extract_atomic_units(section_text)
            context_prefix = (
                " > ".join(heading_stack)
                if heading_stack and self.enable_context_association
                else ""
            )

            for unit_type, content in units:
                tokens = _token_len(content)

                if unit_type in ("code_block", "table"):
                    chunks = self._handle_atomic_unit(
                        content, context_prefix, effective_size
                    )
                    all_chunks.extend(chunks)
                elif unit_type == "heading":
                    all_chunks.append(content)
                else:
                    if tokens > effective_size:
                        sub_chunks = _semantic_split(
                            content,
                            chunk_size=effective_size,
                            overlap=self.chunk_overlap,
                            similarity_threshold=self.similarity_threshold,
                        )
                        all_chunks.extend(sub_chunks)
                    else:
                        all_chunks.append(content)

        return self._merge_short_chunks(all_chunks)

    def _split_flat(self, text: str) -> list[str]:
        """扁平切分（向后兼容）。"""
        units = _extract_atomic_units(text)
        chunks: list[str] = []

        for unit_type, content in units:
            tokens = _token_len(content)

            if unit_type in ("code_block", "table"):
                if tokens > self.chunk_size * 1.5:
                    lines = content.split("\n")
                    sub_chunks = self._merge_lines(lines)
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(content)
            elif unit_type == "heading":
                chunks.append(content)
            else:
                if tokens > self.chunk_size:
                    sub_chunks = _semantic_split(
                        content,
                        chunk_size=self.chunk_size,
                        overlap=self.chunk_overlap,
                        similarity_threshold=self.similarity_threshold,
                    )
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(content)

        return self._merge_short_chunks(chunks)

    def _handle_atomic_unit(
        self, content: str, context_prefix: str, chunk_size: int
    ) -> list[str]:
        """处理代码块/表格，可选注入上下文。"""
        tokens = _token_len(content)

        if tokens > chunk_size * 1.5:
            lines = content.split("\n")
            chunks = self._merge_lines(lines)
            if context_prefix and chunks:
                chunks[0] = f"[Context: {context_prefix}]\n{chunks[0]}"
            return chunks

        if context_prefix:
            content = f"[Context: {context_prefix}]\n{content}"
        return [content]

    def _merge_lines(self, lines: list[str]) -> list[str]:
        """将行列表按 Token 限制合并"""
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for line in lines:
            lt = _token_len(line)
            if current_tokens + lt > self.chunk_size and current:
                chunks.append("\n".join(current))
                overlap_lines: list[str] = []
                overlap_tokens = 0
                for l in reversed(current):
                    lt2 = _token_len(l)
                    if overlap_tokens + lt2 > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, l)
                    overlap_tokens += lt2
                current = overlap_lines + [line]
                current_tokens = overlap_tokens + lt
            else:
                current.append(line)
                current_tokens += lt

        if current:
            chunks.append("\n".join(current))

        return chunks

    def _merge_short_chunks(self, chunks: list[str]) -> list[str]:
        """合并相邻的短 chunk（避免碎片）"""
        if not chunks:
            return []

        merged: list[str] = []
        current = chunks[0]
        current_tokens = _token_len(current)

        for chunk in chunks[1:]:
            ct = _token_len(chunk)
            if current_tokens < self.chunk_size * 0.3 and current_tokens + ct < self.chunk_size * 0.9:
                current += "\n\n" + chunk
                current_tokens += ct
            else:
                merged.append(current)
                current = chunk
                current_tokens = ct

        merged.append(current)
        return merged


class SemanticSplitter:
    """
    语义边界切分：基于 Embedding 相似度，在语义转换处切分。
    支持层次切分（先按 h1/h2 拆分）。
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 100,
        similarity_threshold: float = 0.5,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.similarity_threshold = similarity_threshold

    def split_text(self, text: str) -> list[str]:
        sections = _split_by_major_headings(text)
        chunks: list[str] = []

        for section_text, _heading, _stack in sections:
            units = _extract_atomic_units(section_text)
            for unit_type, content in units:
                if unit_type in ("code_block", "table", "heading"):
                    chunks.append(content)
                else:
                    sub = _semantic_split(
                        content,
                        chunk_size=self.chunk_size,
                        overlap=self.chunk_overlap,
                        similarity_threshold=self.similarity_threshold,
                    )
                    chunks.extend(sub)

        return [c for c in chunks if c.strip()]


class LegacySplitter:
    """兼容旧版的 RecursiveCharacterTextSplitter（字符级）"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 100):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n## ",
                "\n### ",
                "\n#### ",
                "\n\n",
                "\n",
                "。",
                "；",
                "，",
                " ",
                "",
            ],
            length_function=len,
        )

    def split_text(self, text: str) -> list[str]:
        return self._splitter.split_text(text)


# ---- 工厂函数 ----


def create_text_splitter(
    strategy: Literal["markdown", "semantic", "legacy"] = "markdown",
    chunk_size: int = 512,
    chunk_overlap: int = 100,
    similarity_threshold: float = 0.5,
    enable_hierarchical: bool = True,
    enable_adaptive_size: bool = False,
    enable_context_association: bool = True,
):
    """创建文本切分器

    Args:
        strategy: 切分策略
            - "markdown": 结构感知 + Token级 + 语义边界（默认，推荐）
            - "semantic": 纯语义边界切分
            - "legacy": 旧版 RecursiveCharacterTextSplitter
        chunk_size: 目标 chunk 大小（token 数）
        chunk_overlap: 相邻 chunk 重叠（token 数）
        similarity_threshold: 语义相似度阈值（0.0-1.0）
        enable_hierarchical: 先按 h1/h2 层次切分
        enable_adaptive_size: 按内容类型自适应 chunk_size
        enable_context_association: 为代码块/表格注入 heading 上下文
    """
    if strategy == "markdown":
        return MarkdownAwareSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            similarity_threshold=similarity_threshold,
            enable_hierarchical=enable_hierarchical,
            enable_adaptive_size=enable_adaptive_size,
            enable_context_association=enable_context_association,
        )
    elif strategy == "semantic":
        return SemanticSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            similarity_threshold=similarity_threshold,
        )
    elif strategy == "legacy":
        return LegacySplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    else:
        raise ValueError(f"未知切分策略: {strategy}")


# ---- 高层接口 ----


def split_note_to_chunks(note, splitter) -> list[Document]:
    """将单篇 Obsidian 笔记切分为 chunks"""
    from src.parsers.obsidian_parser import classify_domain

    chunks = splitter.split_text(note.content)
    documents: list[Document] = []

    for i, chunk_text in enumerate(chunks):
        if len(chunk_text.strip()) < 20:
            continue

        domain = classify_domain(note.folder)

        # 解析上下文前缀
        context = ""
        clean_text = chunk_text
        if chunk_text.startswith("[Context: "):
            end_idx = chunk_text.find("]\n")
            if end_idx != -1:
                context = chunk_text[10:end_idx]
                clean_text = chunk_text[end_idx + 2 :]

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
            "content_hash": note.content_hash,
            "context": context,
        }

        doc = Document(page_content=clean_text, metadata=metadata)
        documents.append(doc)

    return documents


def split_notes_to_documents(
    notes: list,
    splitter=None,
    chunk_size: int = 512,
    chunk_overlap: int = 100,
) -> list[Document]:
    """批量切分多篇笔记"""
    if splitter is None:
        splitter = create_text_splitter("markdown", chunk_size, chunk_overlap)

    all_docs: list[Document] = []
    for note in notes:
        docs = split_note_to_chunks(note, splitter)
        all_docs.extend(docs)

    return all_docs


# ---- CLI 基准 ----

if __name__ == "__main__":
    import os
    from src.parsers.obsidian_parser import ObsidianParser

    vault = os.getenv(
        "VAULT_PATH",
        "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本",
    )
    parser = ObsidianParser(vault)
    notes = parser.parse_vault()

    print(f"解析到 {len(notes)} 篇笔记")

    for name, strategy in [
        ("MarkdownAware", "markdown"),
        ("Semantic", "semantic"),
        ("Legacy", "legacy"),
    ]:
        splitter = create_text_splitter(
            strategy=strategy, chunk_size=512, chunk_overlap=100
        )
        docs = split_notes_to_documents(notes, splitter=splitter)

        lengths = [len(d.page_content) for d in docs]
        token_lengths = [_token_len(d.page_content) for d in docs]

        print(f"\n=== {name} ===")
        print(f"  chunks: {len(docs)}")
        print(f"  平均字符: {sum(lengths) / len(lengths):.0f}")
        print(f"  平均token: {sum(token_lengths) / len(token_lengths):.0f}")
        print(f"  最大token: {max(token_lengths)}")
        print(
            f"  <100字符占比: {sum(1 for l in lengths if l < 100) / len(lengths) * 100:.1f}%"
        )
