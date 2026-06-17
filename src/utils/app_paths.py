"""Application path resolution for server and desktop modes."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "SecondBrain Chat"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    user_data_dir: Path
    config_dir: Path
    index_dir: Path
    logs_dir: Path
    models_dir: Path
    conversations_db: Path
    auth_db: Path
    audit_db: Path
    metrics_db: Path
    model_config_file: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_desktop_mode() -> bool:
    return os.getenv("SECONDBRAIN_DESKTOP_MODE", "").lower() in {"1", "true", "yes"}


def default_user_data_dir() -> Path:
    override = os.getenv("SECONDBRAIN_USER_DATA_DIR")
    if override:
        return Path(override).expanduser()

    home = Path.home()
    if os.name == "nt":
        return Path(os.getenv("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return home / ".local" / "share" / "secondbrain-chat"


def get_app_paths() -> AppPaths:
    root = project_root()
    if is_desktop_mode():
        user_data = default_user_data_dir()
        config_dir = user_data / "config"
        index_dir = user_data / "index"
        logs_dir = user_data / "logs"
        models_dir = user_data / "models"
    else:
        user_data = root / "data"
        config_dir = user_data
        index_dir = Path(os.getenv("INDEX_DIR", str(user_data / "index")))
        logs_dir = user_data / "logs"
        models_dir = root / "models"

    return AppPaths(
        root=root,
        user_data_dir=user_data,
        config_dir=config_dir,
        index_dir=index_dir,
        logs_dir=logs_dir,
        models_dir=models_dir,
        conversations_db=user_data / "conversations.db",
        auth_db=user_data / "auth.db",
        audit_db=user_data / "audit.db",
        metrics_db=user_data / "metrics.db",
        model_config_file=config_dir / "model_config.json",
    )


def ensure_app_dirs(paths: AppPaths | None = None) -> AppPaths:
    paths = paths or get_app_paths()
    for directory in [
        paths.user_data_dir,
        paths.config_dir,
        paths.index_dir,
        paths.logs_dir,
        paths.models_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return paths
