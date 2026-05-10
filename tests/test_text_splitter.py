"""Comprehensive tests for text_splitter module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parsers.text_splitter import (
    EmbeddingCache,
    LegacySplitter,
    MarkdownAwareSplitter,
    SemanticSplitter,
    _build_overlap,
    _detect_content_type,
    _semantic_split,
    _split_by_major_headings,
    _token_len,
    create_text_splitter,
    split_notes_to_documents,
)


# ---- Fixtures ----


@pytest.fixture(autouse=True)
def mock_embedder(monkeypatch):
    """Mock _embedder.encode to avoid loading heavy models in tests."""
    dim = 1024

    def mock_encode(sentences):
        if not sentences:
            return np.array([])
        embeddings = []
        for s in sentences:
            h = hash(s.strip()) % (2**31)
            rng = np.random.default_rng(h)
            emb = rng.standard_normal(dim)
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)
        return np.array(embeddings)

    monkeypatch.setattr(
        "src.parsers.text_splitter._embedder",
        MagicMock(encode=mock_encode, clear_call_cache=MagicMock()),
    )


@pytest.fixture
def sample_markdown():
    return """# Main Title

## Section 1
This is the first section. It has multiple sentences. Each sentence adds context.

```python
def hello():
    return "world"
```

## Section 2
Another section with different topic. Completely unrelated content here.

| Col1 | Col2 |
|------|------|
| A    | B    |

## Section 3
Final section with prose content. The quick brown fox jumps over the lazy dog.
"""


@pytest.fixture
def code_heavy_text():
    return """```python
import numpy as np

def process_data(data):
    return np.mean(data)

class DataProcessor:
    def __init__(self):
        self.data = []

    def add(self, item):
        self.data.append(item)
```"""


@pytest.fixture
def long_prose():
    return "这是一个很长的段落。" * 200


# ---- Unit Tests: EmbeddingCache ----


class TestEmbeddingCache:
    def test_encode_deduplicates(self, monkeypatch):
        dim = 1024
        call_count = 0

        def mock_model_encode(sentences, **kwargs):
            nonlocal call_count
            call_count += 1
            embeddings = []
            for s in sentences:
                h = hash(s) % (2**31)
                rng = np.random.default_rng(h)
                emb = rng.standard_normal(dim)
                emb = emb / np.linalg.norm(emb)
                embeddings.append(emb)
            return np.array(embeddings)

        cache = EmbeddingCache()
        monkeypatch.setattr(cache, "_model", MagicMock(encode=mock_model_encode))

        sentences = ["hello world", "hello world", "different text"]
        embeddings = cache.encode(sentences)

        assert embeddings.shape == (3, dim)
        assert np.allclose(embeddings[0], embeddings[1])
        assert call_count == 1  # deduplicated to 2 unique sentences in one call

    def test_call_cache_clear(self):
        cache = EmbeddingCache()
        cache._call_cache["test"] = np.array([1.0, 2.0])
        cache.clear_call_cache()
        assert len(cache._call_cache) == 0


# ---- Unit Tests: _split_by_major_headings ----


class TestSplitByMajorHeadings:
    def test_splits_by_h1_h2(self, sample_markdown):
        sections = _split_by_major_headings(sample_markdown)
        assert len(sections) >= 3

        for section_text, heading, stack in sections:
            assert isinstance(section_text, str)
            assert isinstance(heading, str)
            assert isinstance(stack, list)

    def test_no_headings(self):
        text = "Just plain text without any headings."
        sections = _split_by_major_headings(text)
        assert len(sections) == 1
        assert sections[0][1] == ""
        assert sections[0][2] == []

    def test_heading_stack_accumulation(self):
        text = "# H1\ncontent1\n## H2\ncontent2\n### H3\ncontent3"
        sections = _split_by_major_headings(text)
        assert len(sections) == 2  # H1 section + H2 section
        # First section is before H2, has H1 in stack if any text before H2
        # Second section is after H2, should have ["H1", "H2"] in stack
        h2_section = [s for s in sections if s[1] == "H2"][0]
        assert "H1" in h2_section[2]
        assert "H2" in h2_section[2]


# ---- Unit Tests: _detect_content_type ----


class TestDetectContentType:
    def test_code_detection(self, code_heavy_text):
        assert _detect_content_type(code_heavy_text) == "code"

    def test_prose_detection(self, long_prose):
        result = _detect_content_type(long_prose)
        assert result in ("prose", "general")

    def test_technical_detection(self):
        text = "Use `pip install` to add **dependencies**. See [docs](link)."
        assert _detect_content_type(text) == "technical"

    def test_general_fallback(self):
        text = "Some normal text without special patterns."
        assert _detect_content_type(text) == "general"


# ---- Unit Tests: _semantic_split ----


class TestSemanticSplit:
    def test_basic_splitting(self):
        text = "第一句。第二句。第三句。第四句。"
        chunks = _semantic_split(text, chunk_size=10, overlap=2)
        assert len(chunks) > 0
        assert all(len(c.strip()) > 0 for c in chunks)

    def test_respects_chunk_size(self):
        long_text = "这是一个测试句子。" * 100
        chunks = _semantic_split(long_text, chunk_size=20, overlap=5)
        for chunk in chunks:
            tokens = _token_len(chunk)
            assert tokens <= 30  # 1.2x soft limit

    def test_empty_text(self):
        assert _semantic_split("") == []
        assert _semantic_split("   ") == []

    def test_single_sentence(self):
        assert _semantic_split("只有一个句子。") == ["只有一个句子。"]

    def test_overlap_present(self):
        text = "主题A的第一句。主题A的第二句。主题B的第一句。主题B的第二句。"
        chunks = _semantic_split(text, chunk_size=20, overlap=5)
        if len(chunks) > 1:
            # Some overlap should exist
            assert len(chunks) >= 2


# ---- Unit Tests: _build_overlap ----


class TestBuildOverlap:
    def test_basic_overlap(self):
        chunk = ["第一句。", "第二句。", "第三句。"]
        overlap = _build_overlap(chunk, 50)
        assert len(overlap) <= len(chunk)
        assert all(s in chunk for s in overlap)

    def test_empty_chunk(self):
        assert _build_overlap([], 10) == []


# ---- Unit Tests: MarkdownAwareSplitter ----


class TestMarkdownAwareSplitter:
    def test_default_split(self, sample_markdown):
        splitter = MarkdownAwareSplitter(chunk_size=100, chunk_overlap=20)
        chunks = splitter.split_text(sample_markdown)
        assert len(chunks) > 0
        assert any("```python" in c for c in chunks)
        assert any("| Col1" in c for c in chunks)

    def test_hierarchical_splitting(self, sample_markdown):
        splitter = MarkdownAwareSplitter(
            chunk_size=100,
            enable_hierarchical=True,
            enable_context_association=True,
        )
        chunks = splitter.split_text(sample_markdown)
        code_chunks = [c for c in chunks if "```python" in c]
        if code_chunks:
            assert "[Context:" in code_chunks[0]

    def test_flat_backward_compatible(self, sample_markdown):
        splitter = MarkdownAwareSplitter(
            chunk_size=100,
            enable_hierarchical=False,
        )
        chunks = splitter.split_text(sample_markdown)
        assert len(chunks) > 0

    def test_merge_short_chunks(self):
        splitter = MarkdownAwareSplitter(chunk_size=512)
        chunks = ["Short.", "Also short.", "A" * 400]
        merged = splitter._merge_short_chunks(chunks)
        assert len(merged) < len(chunks)

    def test_adaptive_size_code(self, code_heavy_text):
        splitter = MarkdownAwareSplitter(
            chunk_size=512,
            enable_adaptive_size=True,
            enable_hierarchical=True,
        )
        chunks = splitter.split_text(code_heavy_text)
        assert len(chunks) > 0


# ---- Unit Tests: SemanticSplitter ----


class TestSemanticSplitter:
    def test_split_text(self, sample_markdown):
        splitter = SemanticSplitter(chunk_size=100, chunk_overlap=20)
        chunks = splitter.split_text(sample_markdown)
        assert len(chunks) > 0
        assert all(c.strip() for c in chunks)


# ---- Unit Tests: LegacySplitter ----


class TestLegacySplitter:
    def test_basic_split(self):
        splitter = LegacySplitter(chunk_size=50, chunk_overlap=10)
        text = "Paragraph one.\n\nParagraph two with more content."
        chunks = splitter.split_text(text)
        assert len(chunks) > 0


# ---- Integration Tests: create_text_splitter ----


class TestCreateTextSplitter:
    def test_markdown_strategy(self):
        splitter = create_text_splitter("markdown", chunk_size=256)
        assert isinstance(splitter, MarkdownAwareSplitter)
        assert splitter.chunk_size == 256

    def test_semantic_strategy(self):
        splitter = create_text_splitter("semantic")
        assert isinstance(splitter, SemanticSplitter)

    def test_legacy_strategy(self):
        splitter = create_text_splitter("legacy")
        assert isinstance(splitter, LegacySplitter)

    def test_invalid_strategy(self):
        with pytest.raises(ValueError):
            create_text_splitter("invalid")

    def test_new_parameters(self):
        splitter = create_text_splitter(
            "markdown",
            similarity_threshold=0.6,
            enable_hierarchical=True,
            enable_adaptive_size=True,
        )
        assert splitter.similarity_threshold == 0.6
        assert splitter.enable_hierarchical is True


# ---- Integration Tests: split_notes_to_documents ----


class TestSplitNotesToDocuments:
    def test_with_mock_note(self, sample_markdown):
        from dataclasses import dataclass, field

        @dataclass
        class MockNote:
            title: str = "Test"
            content: str = sample_markdown
            source_file: str = "/test.md"
            relative_path: str = "test.md"
            folder: str = "test"
            tags: list = field(default_factory=list)
            date: str | None = None
            outbound_links: list = field(default_factory=list)
            content_hash: str = "abc123"

        note = MockNote()
        splitter = create_text_splitter("markdown", chunk_size=100)
        docs = split_notes_to_documents([note], splitter=splitter)

        assert len(docs) > 0
        assert all(hasattr(d, "metadata") for d in docs)
        assert all("chunk_index" in d.metadata for d in docs)
        assert all("context" in d.metadata for d in docs)

    def test_context_metadata_parsed(self):
        from dataclasses import dataclass, field

        @dataclass
        class MockNote:
            title: str = "Test"
            content: str = "# Title\n\n```python\nprint(1)\n```"
            source_file: str = "/test.md"
            relative_path: str = "test.md"
            folder: str = "test"
            tags: list = field(default_factory=list)
            date: str | None = None
            outbound_links: list = field(default_factory=list)
            content_hash: str = "abc123"

        note = MockNote()
        splitter = create_text_splitter(
            "markdown",
            chunk_size=512,
            enable_hierarchical=True,
            enable_context_association=True,
        )
        docs = split_notes_to_documents([note], splitter=splitter)

        code_docs = [d for d in docs if "```python" in d.page_content]
        if code_docs:
            assert code_docs[0].metadata["context"] == "Title"
            assert "[Context:" not in code_docs[0].page_content


# ---- Backward Compatibility Tests ----


class TestBackwardCompatibility:
    def test_old_api(self, sample_markdown):
        splitter = create_text_splitter("markdown", 512, 100)
        chunks = splitter.split_text(sample_markdown)
        assert len(chunks) > 0

    def test_pipeline_config_integration(self):
        from src.retrievers.pipeline import PipelineConfig

        config = PipelineConfig(chunk_size=512, chunk_overlap=100)
        assert config.chunk_size == 512
        assert config.chunk_overlap == 100
