"""笔记管理 FastAPI 路由

所有端点前缀为 /api/v1，在 app.py 中通过 include_router 注册。
"""

import os

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, FileResponse

from src.api.notes import (
    list_notes,
    get_note,
    create_note,
    update_note,
    delete_note,
    search_notes,
    search_notes_by_keyword,
    list_notes_tree,
    list_folders,
    list_tags,
    safe_path,
)
from src.models.notes import (
    NoteCreateRequest,
    NoteUpdateRequest,
    NoteListResponse,
    NoteTreeResponse,
    NoteDetail,
    FolderListResponse,
    TagListResponse,
)
from src.utils.audit_logger import audit_log, AuditAction
from src.utils.logger import log
from src.utils.vault_git import GitSyncError, commit_and_push_vault_change

VAULT_PATH = os.getenv(
    "VAULT_PATH",
    "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本",
)

router = APIRouter()


def _writeback_enabled() -> bool:
    return os.getenv("VAULT_GIT_WRITEBACK", "false").lower() in {"true", "1", "yes"}


def _maybe_writeback_note_change(action: str, relative_path: str) -> JSONResponse | None:
    if not _writeback_enabled():
        return None
    try:
        commit_and_push_vault_change(VAULT_PATH, action, relative_path)
    except GitSyncError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Git writeback failed: {str(e)}"})
    return None


# ---- 搜索必须在 /notes/{path} 之前注册，否则 "search" 会被当作路径参数 ----


@router.get("/notes/search")
async def api_search_notes(
    request: Request,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    top_k: int = Query(20, ge=1, le=50, description="返回结果数"),
    domain: str | None = Query(None, description="领域过滤"),
):
    """全文搜索笔记（RAG 向量检索）"""
    # 延迟导入 pipeline，避免循环引用
    from src.api.app import pipeline as app_pipeline

    results = search_notes(app_pipeline, q, top_k=top_k, domain_filter=domain)
    audit_log(
        AuditAction.NOTE_SEARCH,
        request,
        details={"action": "search", "query": q, "domain": domain},
    )
    return {"results": results}


@router.get("/notes/keyword-search")
async def api_search_notes_by_keyword(
    request: Request,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    top_k: int = Query(20, ge=1, le=50, description="返回结果数"),
):
    """关键词搜索笔记（标题 + 正文，按时间倒序）"""
    results = search_notes_by_keyword(VAULT_PATH, q, top_k=top_k)
    audit_log(
        AuditAction.NOTE_SEARCH,
        request,
        details={"action": "keyword_search", "query": q, "count": len(results)},
    )
    return {"results": results}


@router.get("/notes", response_model=NoteListResponse)
async def api_list_notes(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    folder: str | None = Query(None, description="按文件夹过滤"),
    domain: str | None = Query(None, description="按领域过滤"),
    tag: str | None = Query(None, description="按标签过滤"),
    keyword: str | None = Query(None, description="按标题关键词过滤"),
):
    """列出笔记（支持分页和多维度过滤）"""
    result = list_notes(
        VAULT_PATH,
        page=page,
        page_size=page_size,
        folder=folder,
        domain=domain,
        tag=tag,
        keyword=keyword,
    )
    audit_log(
        AuditAction.NOTE_SEARCH,
        request,
        details={"action": "list", "folder": folder, "domain": domain, "keyword": keyword},
    )
    return result


@router.get("/notes/tree", response_model=NoteTreeResponse, response_model_exclude_none=True)
async def api_list_notes_tree(
    request: Request,
    domain: str | None = Query(None, description="按领域过滤"),
    tag: str | None = Query(None, description="按标签过滤"),
    keyword: str | None = Query(None, description="按标题关键词过滤"),
):
    """列出笔记树（文件夹 + 笔记混合层级）"""
    result = list_notes_tree(
        VAULT_PATH,
        domain=domain,
        tag=tag,
        keyword=keyword,
    )
    audit_log(
        AuditAction.NOTE_SEARCH,
        request,
        details={"action": "tree", "domain": domain, "tag": tag, "keyword": keyword},
    )
    return result


@router.get("/notes/{relative_path:path}", response_model=NoteDetail)
async def api_get_note(request: Request, relative_path: str):
    """获取单个笔记详情"""
    note = get_note(VAULT_PATH, relative_path)
    audit_log(
        AuditAction.NOTE_SEARCH,
        request,
        details={"action": "get", "path": relative_path},
    )
    return note


@router.post("/notes", response_model=NoteDetail)
async def api_create_note(request: Request, body: NoteCreateRequest):
    """新建 Markdown 笔记"""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(
            status_code=401, content={"error": "需要登录后才能创建笔记"}
        )

    note = create_note(
        VAULT_PATH,
        relative_path=body.relative_path,
        title=body.title,
        content=body.content,
        tags=body.tags,
        date=body.date,
        frontmatter=body.frontmatter,
    )

    # 触发增量索引重建
    from src.api.app import pipeline as app_pipeline

    if app_pipeline:
        try:
            app_pipeline.build_index(incremental=True)
        except Exception as e:
            log.warning("增量索引重建失败: %s", e)

    writeback_error = _maybe_writeback_note_change("create", body.relative_path)
    if writeback_error is not None:
        return writeback_error

    audit_log(
        AuditAction.NOTE_CREATE,
        request,
        details={"path": body.relative_path, "title": body.title},
    )
    return note


@router.put("/notes/{relative_path:path}", response_model=NoteDetail)
async def api_update_note(
    request: Request, relative_path: str, body: NoteUpdateRequest
):
    """更新 Markdown 笔记"""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(
            status_code=401, content={"error": "需要登录后才能编辑笔记"}
        )

    note = update_note(
        VAULT_PATH,
        relative_path=relative_path,
        content=body.content,
        tags=body.tags,
        date=body.date,
        frontmatter=body.frontmatter,
    )

    from src.api.app import pipeline as app_pipeline

    if app_pipeline:
        try:
            app_pipeline.build_index(incremental=True)
        except Exception as e:
            log.warning("增量索引重建失败: %s", e)

    writeback_error = _maybe_writeback_note_change("update", relative_path)
    if writeback_error is not None:
        return writeback_error

    audit_log(
        AuditAction.NOTE_UPDATE,
        request,
        details={"path": relative_path},
    )
    return note


@router.delete("/notes/{relative_path:path}")
async def api_delete_note(request: Request, relative_path: str):
    """删除笔记"""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(
            status_code=401, content={"error": "需要登录后才能删除笔记"}
        )

    delete_note(VAULT_PATH, relative_path)

    from src.api.app import pipeline as app_pipeline

    if app_pipeline:
        try:
            app_pipeline.build_index(incremental=True)
        except Exception as e:
            log.warning("增量索引重建失败: %s", e)

    writeback_error = _maybe_writeback_note_change("delete", relative_path)
    if writeback_error is not None:
        return writeback_error

    audit_log(
        AuditAction.NOTE_DELETE,
        request,
        details={"path": relative_path},
    )
    return {"status": "ok"}


@router.get("/folders", response_model=FolderListResponse)
async def api_list_folders(request: Request):
    """列出 vault 中所有包含文档的文件夹"""
    folders = list_folders(VAULT_PATH)
    return {"folders": folders}


@router.get("/tags", response_model=TagListResponse, response_model_exclude_none=True)
async def api_list_tags(request: Request, with_count: bool = Query(True)):
    """列出所有标签（默认带使用次数）"""
    tags = list_tags(VAULT_PATH)
    if not with_count:
        tags = [{"name": t["name"]} for t in tags]
    return {"tags": tags}


@router.get("/documents/download/{relative_path:path}")
async def api_download_document(request: Request, relative_path: str):
    """下载非 Markdown 文档"""
    file_path = safe_path(VAULT_PATH, relative_path)
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"error": "文件不存在"})

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )
