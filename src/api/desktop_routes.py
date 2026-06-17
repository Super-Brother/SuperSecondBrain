"""Desktop-specific API routes."""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.utils.app_paths import get_app_paths, is_desktop_mode
from src.utils.background_tasks import task_registry
from src.utils.desktop_config import DesktopConfig, load_desktop_config, save_desktop_config


router = APIRouter()


class ImportDataRequest(BaseModel):
    source_data_dir: str
    overwrite: bool = False


class OpenSourceRequest(BaseModel):
    target: str


@router.get("/desktop/status")
async def desktop_status():
    cfg = load_desktop_config()
    paths = get_app_paths()
    index_loaded = False
    stats = {}
    try:
        from src.api.app import pipeline

        if pipeline is not None:
            index_loaded = pipeline.rag_retriever is not None
            stats = pipeline.get_stats()
    except Exception:
        stats = {}

    return {
        "desktop_mode": is_desktop_mode(),
        "onboarding_complete": cfg.onboarding_complete,
        "vault_path": cfg.vault_path,
        "user_data_dir": str(paths.user_data_dir),
        "index_dir": str(paths.index_dir),
        "index_loaded": index_loaded,
        "stats": stats,
    }


@router.post("/desktop/config")
async def update_desktop_config(body: DesktopConfig):
    saved = save_desktop_config(body)
    return {"status": "ok", "config": asdict(saved)}


@router.post("/desktop/import-data")
async def import_data(body: ImportDataRequest):
    source = Path(body.source_data_dir).expanduser()
    if not source.exists() or not source.is_dir():
        return JSONResponse(status_code=400, content={"error": "source_data_dir does not exist"})

    paths = get_app_paths()
    paths.user_data_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    items = [
        "conversations.db",
        "auth.db",
        "audit.db",
        "metrics.db",
        "model_config.json",
        "index",
    ]

    for item in items:
        src = source / item
        if not src.exists():
            skipped.append(item)
            continue

        dst = (paths.config_dir / item) if item == "model_config.json" else (paths.user_data_dir / item)
        if dst.exists() and not body.overwrite:
            skipped.append(item)
            warnings.append(f"{item} already exists; pass overwrite=true to replace it")
            continue

        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()

        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(item)

    return {"status": "ok", "copied": copied, "skipped": skipped, "warnings": warnings}


@router.post("/index/build")
async def start_index_build():
    from src.api.app import pipeline

    if pipeline is None:
        return JSONResponse(status_code=503, content={"error": "Pipeline not initialized"})

    def build():
        return pipeline.rebuild_index_from_vault()

    task = task_registry.start("index_build", build)
    return {"task_id": task.task_id, "status": task.status}


@router.get("/index/tasks/{task_id}")
async def get_index_task(task_id: str):
    task = task_registry.as_dict(task_id)
    if task is None:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return task


@router.post("/desktop/open-source")
async def normalize_open_source(body: OpenSourceRequest):
    return {"target": body.target}
