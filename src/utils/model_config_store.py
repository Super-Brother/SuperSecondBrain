"""模型配置持久化存储

将用户在 UI 中选择的 LLM 配置落盘到 JSON 文件，
确保服务重启后仍能恢复，避免每次刷新页面都丢失配置。
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


CONFIG_FILE = os.getenv("MODEL_CONFIG_FILE", "data/model_config.json")


@dataclass(frozen=True)
class StoredModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    preset: Optional[str] = None  # 记录用户选了哪个预设（"custom" 或 preset key）


def load_config() -> Optional[StoredModelConfig]:
    """读取持久化的模型配置；首次启动或文件损坏时返回 None。"""
    path = Path(CONFIG_FILE)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return StoredModelConfig(
            base_url=data["base_url"],
            api_key=data.get("api_key", ""),
            model=data["model"],
            temperature=float(data.get("temperature", 0.3)),
            preset=data.get("preset"),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_config(cfg: StoredModelConfig) -> None:
    """将模型配置写入 JSON 文件。"""
    path = Path(CONFIG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
