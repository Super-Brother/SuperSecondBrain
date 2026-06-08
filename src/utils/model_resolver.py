"""模型路径解析工具

优先使用本地 models/ 目录下的模型，避免重复从 HuggingFace 下载。
"""

import os
from pathlib import Path


def _get_project_root() -> Path:
    """获取项目根目录（src/ 的上级）"""
    return Path(__file__).parent.parent.parent


def resolve_model_path(model_name_or_path: str) -> str:
    """解析模型路径：优先本地 models/ 目录，回退到 HuggingFace 模型名

    优先级：
    1. 如果传入的已经是本地存在的绝对/相对路径，直接使用
    2. 检查项目根目录下的 models/<model_name> 是否存在
    3. 以上都不满足，返回原始 HuggingFace 模型名（如 BAAI/bge-large-zh-v1.5）
    """
    # 已经是本地路径且存在
    if os.path.isdir(model_name_or_path):
        return model_name_or_path

    # 检查项目本地 models/ 目录（支持两种命名：BAAI_bge-large-zh-v1.5 或 bge-large-zh-v1.5）
    project_root = _get_project_root()
    candidates = [
        model_name_or_path.replace("/", "_"),  # BAAI_bge-large-zh-v1.5
        model_name_or_path.split("/")[-1],      # bge-large-zh-v1.5
    ]
    for cand in candidates:
        local_path = project_root / "models" / cand
        if local_path.is_dir():
            return str(local_path)

    # 回退到 HuggingFace 模型名
    return model_name_or_path
