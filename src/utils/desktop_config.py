"""Desktop configuration storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.utils.app_paths import get_app_paths


@dataclass(frozen=True)
class DesktopConfig:
    vault_path: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "qwen2.5:3b"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    onboarding_complete: bool = False


def config_path() -> Path:
    return get_app_paths().config_dir / "desktop_config.json"


def load_desktop_config() -> DesktopConfig:
    path = config_path()
    if not path.exists():
        return DesktopConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DesktopConfig()
    return DesktopConfig(
        vault_path=str(data.get("vault_path", "")),
        llm_base_url=str(data.get("llm_base_url", "http://localhost:11434/v1")),
        llm_api_key=str(data.get("llm_api_key", "not-needed")),
        llm_model=str(data.get("llm_model", "qwen2.5:3b")),
        embedding_model=str(data.get("embedding_model", "BAAI/bge-large-zh-v1.5")),
        reranker_model=str(data.get("reranker_model", "BAAI/bge-reranker-base")),
        onboarding_complete=bool(data.get("onboarding_complete", False)),
    )


def save_desktop_config(cfg: DesktopConfig) -> DesktopConfig:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg
