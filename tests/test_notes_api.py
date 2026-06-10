"""测试笔记管理 API"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 模块级临时 vault
_module_vault: Path | None = None


def _setup_vault():
    """创建临时 vault 并返回路径"""
    global _module_vault
    if _module_vault is not None:
        return _module_vault

    vault = Path(tempfile.mkdtemp(prefix="sb_test_vault_"))
    _module_vault = vault

    # Markdown 测试笔记（带 frontmatter）
    (vault / "测试笔记.md").write_text(
        "---\ntags: [测试, 标签]\ndate: 2024-01-01\n---\n# 测试笔记\n\n这是测试内容。\n",
        encoding="utf-8",
    )

    # 子目录中的笔记
    subdir = vault / "子目录"
    subdir.mkdir()
    (subdir / "子笔记.md").write_text(
        "# 子笔记\n\n子目录中的内容。\n",
        encoding="utf-8",
    )

    # 非 Markdown 文件
    (vault / "文档.pdf").write_text("fake pdf content", encoding="utf-8")

    return vault


def _mock_verify_token(token):
    if token == "test-token":
        return {"username": "testuser", "email": "test@example.com"}
    return None


@pytest.fixture(scope="module")
def client():
    """创建 TestClient，使用临时 vault 目录（模块级只创建一次）"""
    vault = _setup_vault()

    with (
        patch("src.api.app.pipeline") as mock_pipeline,
        patch("src.api.app.conv_manager") as mock_conv,
        patch("src.api.notes_routes.VAULT_PATH", str(vault)),
        patch("src.api.notes_routes.audit_log") as _,
        patch("src.api.auth.verify_token", side_effect=_mock_verify_token),
    ):
        mock_pipeline.rag_retriever = MagicMock()
        mock_pipeline.get_stats.return_value = {
            "total_notes": 2,
            "total_chunks": 4,
            "domain_distribution": {"其他": 2},
        }
        mock_pipeline.build_index.return_value = mock_pipeline.get_stats.return_value

        mock_conv.create_session.return_value = "test-session-id"
        mock_conv.get_history.return_value = []

        from src.api.app import app

        with TestClient(app) as c:
            yield c


AUTH_HEADER = {"Authorization": "Bearer test-token"}


class TestListNotes:
    """测试列出笔记"""

    def test_list_notes(self, client):
        r = client.get("/api/v1/notes")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 2
        assert len(d["items"]) >= 2

    def test_list_notes_pagination(self, client):
        r = client.get("/api/v1/notes?page=1&page_size=1")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 2
        assert len(d["items"]) == 1
        assert d["page"] == 1
        assert d["page_size"] == 1

    def test_list_notes_filter_by_folder(self, client):
        r = client.get("/api/v1/notes?folder=子目录")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["folder"] == "子目录"

    def test_list_notes_filter_by_tag(self, client):
        r = client.get("/api/v1/notes?tag=测试")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert "测试" in d["items"][0]["tags"]

    def test_list_notes_filter_by_domain(self, client):
        r = client.get("/api/v1/notes?domain=其他")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 1

    def test_list_notes_keyword(self, client):
        r = client.get("/api/v1/notes?keyword=子笔记")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert "子笔记" in d["items"][0]["title"]


class TestGetNote:
    """测试获取笔记详情"""

    def test_get_markdown_note(self, client):
        r = client.get("/api/v1/notes/测试笔记.md")
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "测试笔记"
        assert d["format"] == "markdown"
        assert "测试内容" in d["content"]
        assert d["tags"] == ["测试", "标签"]
        assert d["date"] == "2024-01-01"
        assert d["is_downloadable"] is False

    def test_get_non_markdown_note(self, client):
        r = client.get("/api/v1/notes/文档.pdf")
        assert r.status_code == 200
        d = r.json()
        assert d["format"] == "pdf"
        assert d["is_downloadable"] is True

    def test_get_note_not_found(self, client):
        r = client.get("/api/v1/notes/不存在的笔记.md")
        assert r.status_code == 404


class TestCreateNote:
    """测试新建笔记"""

    def test_create_note_success(self, client):
        body = {
            "relative_path": "新建/新笔记.md",
            "title": "新笔记",
            "content": "这是新建的笔记内容。",
            "tags": ["新标签"],
            "date": "2024-06-10",
        }
        r = client.post("/api/v1/notes", json=body, headers=AUTH_HEADER)
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "新笔记"
        assert d["relative_path"] == "新建/新笔记.md"
        assert "新标签" in d["tags"]

    def test_create_note_anonymous_rejected(self, client):
        body = {
            "relative_path": "新笔记.md",
            "title": "新笔记",
            "content": "内容",
        }
        r = client.post("/api/v1/notes", json=body)
        assert r.status_code == 401

    def test_create_note_duplicate_rejected(self, client):
        body = {
            "relative_path": "测试笔记.md",
            "title": "重复",
            "content": "内容",
        }
        r = client.post("/api/v1/notes", json=body, headers=AUTH_HEADER)
        assert r.status_code == 409

    def test_create_note_invalid_extension(self, client):
        body = {
            "relative_path": "恶意文件.pdf",
            "title": "恶意",
            "content": "内容",
        }
        r = client.post("/api/v1/notes", json=body, headers=AUTH_HEADER)
        assert r.status_code == 400


class TestUpdateNote:
    """测试更新笔记"""

    def test_update_note_content(self, client):
        body = {"content": "更新后的内容。"}
        r = client.put(
            "/api/v1/notes/测试笔记.md",
            json=body,
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        d = r.json()
        assert "更新后的内容" in d["content"]

    def test_update_note_tags(self, client):
        body = {"tags": ["更新标签"]}
        r = client.put(
            "/api/v1/notes/测试笔记.md",
            json=body,
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["tags"] == ["更新标签"]

    def test_update_note_anonymous_rejected(self, client):
        body = {"content": "内容"}
        r = client.put("/api/v1/notes/测试笔记.md", json=body)
        assert r.status_code == 401

    def test_update_note_not_found(self, client):
        body = {"content": "内容"}
        r = client.put(
            "/api/v1/notes/不存在.md",
            json=body,
            headers=AUTH_HEADER,
        )
        assert r.status_code == 404


class TestDeleteNote:
    """测试删除笔记"""

    def test_delete_note_success(self, client):
        r = client.delete(
            "/api/v1/notes/测试笔记.md",
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        # 确认已删除
        r2 = client.get("/api/v1/notes/测试笔记.md")
        assert r2.status_code == 404

    def test_delete_note_anonymous_rejected(self, client):
        r = client.delete("/api/v1/notes/测试笔记.md")
        assert r.status_code == 401

    def test_delete_note_not_found(self, client):
        r = client.delete(
            "/api/v1/notes/不存在.md",
            headers=AUTH_HEADER,
        )
        assert r.status_code == 404


class TestSearchNotes:
    """测试搜索笔记"""

    def test_search_notes(self, client):
        with patch("src.api.app.pipeline") as mock_pipeline:
            mock_pipeline.rag_retriever = MagicMock()
            from langchain_core.documents import Document

            mock_doc = Document(
                page_content="搜索结果片段",
                metadata={
                    "title": "测试笔记",
                    "relative_path": "测试笔记.md",
                    "folder": "root",
                    "domain": "其他",
                    "tags": ["测试"],
                    "content_hash": "abc123",
                },
            )
            mock_pipeline.rag_retriever.retrieve.return_value = [
                (mock_doc, 0.85),
            ]

            r = client.get("/api/v1/notes/search?q=测试")
            assert r.status_code == 200
            d = r.json()
            assert "results" in d
            assert len(d["results"]) == 1
            assert d["results"][0]["score"] == 0.85


class TestFoldersAndTags:
    """测试文件夹和标签列表"""

    def test_list_folders(self, client):
        r = client.get("/api/v1/folders")
        assert r.status_code == 200
        d = r.json()
        assert "root" in d["folders"]
        assert "子目录" in d["folders"]

    def test_list_tags(self, client):
        r = client.get("/api/v1/tags")
        assert r.status_code == 200
        d = r.json()
        tags = [t["name"] for t in d["tags"]]
        assert "测试" in tags
        assert "标签" in tags

    def test_list_tags_without_count(self, client):
        r = client.get("/api/v1/tags?with_count=false")
        assert r.status_code == 200
        d = r.json()
        assert all("count" not in t for t in d["tags"])


class TestDownloadDocument:
    """测试文档下载"""

    def test_download_exists(self, client):
        r = client.get("/api/v1/documents/download/文档.pdf")
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")

    def test_download_not_found(self, client):
        r = client.get("/api/v1/documents/download/不存在.pdf")
        assert r.status_code == 404


class TestSecurity:
    """测试安全边界"""

    def test_path_traversal_in_get(self, client):
        r = client.get("/api/v1/notes/../.env")
        assert r.status_code == 400

    def test_path_traversal_in_create(self, client):
        body = {
            "relative_path": "../../etc/passwd",
            "title": "恶意",
            "content": "内容",
        }
        r = client.post("/api/v1/notes", json=body, headers=AUTH_HEADER)
        assert r.status_code == 400

    def test_path_traversal_in_delete(self, client):
        r = client.delete(
            "/api/v1/notes/../../.env",
            headers=AUTH_HEADER,
        )
        assert r.status_code == 400

    def test_empty_path_rejected(self, client):
        r = client.get("/api/v1/notes/")
        # FastAPI 可能重定向或返回 404，取决于路由匹配
        assert r.status_code in (404, 307, 308)
