"""索引版本管理器

支持多版本索引并存、原子切换、自动清理和回滚。

目录结构：
    data/index/
    ├── versions/
    │   ├── 20250610_143022_abc123/   # 版本目录
    │   └── 20250610_153045_def456/   # 当前激活版本
    ├── current_version.json          # {"current": "...", "updated_at": "..."}
    └── (legacy files)                # 兼容旧版本的无版本化文件

Usage:
    from src.utils.index_version import IndexVersionManager
    vm = IndexVersionManager("data/index")
    version_id = vm.create_version_dir()
    # ... 构建索引到 version_id 目录 ...
    vm.switch_version(version_id)
    versions = vm.list_versions()
    vm.rollback()  # 回滚到上一个版本
"""

import json
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


class IndexVersionManager:
    """索引版本管理器"""

    def __init__(self, base_dir: str = "data/index", max_versions: int = 5):
        self.base_dir = Path(base_dir)
        self.versions_dir = self.base_dir / "versions"
        self.current_file = self.base_dir / "current_version.json"
        self.max_versions = max_versions
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保目录结构存在"""
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def _generate_version_id(self) -> str:
        """生成版本 ID：YYYYMMDD_HHMMSS_xxxxxx"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(3)  # 6 位十六进制随机后缀，避免同一秒内冲突
        return f"{timestamp}_{suffix}"

    def create_version_dir(self) -> str:
        """创建新版本目录，返回版本 ID"""
        version_id = self._generate_version_id()
        version_path = self.versions_dir / version_id
        version_path.mkdir(parents=True, exist_ok=True)
        return version_id

    def get_version_path(self, version_id: str) -> Path:
        """获取指定版本的目录路径"""
        return self.versions_dir / version_id

    def get_current_version(self) -> str | None:
        """获取当前激活的版本 ID"""
        if self.current_file.exists():
            try:
                data = json.loads(self.current_file.read_text(encoding="utf-8"))
                return data.get("current")
            except Exception:
                pass

        # 向后兼容：检查旧版无版本化索引
        legacy_files = ["faiss.index", "documents.pkl", "bm25.pkl"]
        if any((self.base_dir / f).exists() for f in legacy_files):
            return "__legacy__"

        return None

    def get_current_index_dir(self) -> str:
        """获取当前应使用的索引目录（供 Pipeline.load_index 使用）"""
        current = self.get_current_version()
        if current == "__legacy__":
            return str(self.base_dir)
        if current:
            return str(self.get_version_path(current))
        return str(self.base_dir)

    def switch_version(self, version_id: str) -> dict[str, Any]:
        """原子切换到指定版本"""
        version_path = self.get_version_path(version_id)
        if not version_path.exists():
            raise ValueError(f"版本不存在: {version_id}")

        # 验证版本目录包含必要的索引文件
        required_files = ["faiss.index", "documents.pkl", "bm25.pkl"]
        missing = [f for f in required_files if not (version_path / f).exists()]
        if missing:
            raise ValueError(f"版本 {version_id} 缺少必要文件: {missing}")

        # 写入当前版本（原子操作：先写临时文件再重命名）
        data = {
            "current": version_id,
            "updated_at": datetime.now().isoformat(),
            "previous": self.get_current_version(),
        }
        temp_file = self.current_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.current_file)

        return {
            "status": "ok",
            "version": version_id,
            "previous": data["previous"],
        }

    def rollback(self) -> dict[str, Any]:
        """回滚到上一个版本"""
        if not self.current_file.exists():
            raise RuntimeError("没有版本记录，无法回滚")

        data = json.loads(self.current_file.read_text(encoding="utf-8"))
        previous = data.get("previous")

        if not previous or previous == "__legacy__":
            raise RuntimeError("没有上一个版本可供回滚")

        return self.switch_version(previous)

    def list_versions(self) -> list[dict[str, Any]]:
        """列出所有版本（按时间倒序）"""
        if not self.versions_dir.exists():
            return []

        versions = []
        current = self.get_current_version()

        for v_dir in sorted(self.versions_dir.iterdir(), key=lambda p: p.name, reverse=True):
            if not v_dir.is_dir():
                continue

            version_id = v_dir.name
            stats_file = v_dir / "stats.json"
            stats = {}
            if stats_file.exists():
                try:
                    stats = json.loads(stats_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 计算目录大小
            try:
                size_mb = sum(f.stat().st_size for f in v_dir.rglob("*") if f.is_file()) / (1024 * 1024)
            except Exception:
                size_mb = 0

            versions.append({
                "version_id": version_id,
                "is_current": version_id == current,
                "size_mb": round(size_mb, 2),
                "stats": stats,
            })

        return versions

    def cleanup_old_versions(self) -> list[str]:
        """清理超过保留数量的旧版本，返回删除的版本 ID 列表（当前版本不会被删除）"""
        versions = [v for v in self.versions_dir.iterdir() if v.is_dir()]
        versions.sort(key=lambda p: p.name, reverse=True)

        current = self.get_current_version()
        deleted = []
        to_remove = versions[self.max_versions :]

        for old in to_remove:
            if old.name == current:
                # 当前版本在待删除列表中，尝试删除更旧的一个版本（在 to_remove 中找）
                continue
            try:
                shutil.rmtree(old)
                deleted.append(old.name)
            except Exception as e:
                print(f"[IndexVersionManager] 清理旧版本失败 {old.name}: {e}")

        # 如果由于保护了当前版本导致仍然超限，再删一个非当前的最旧版本
        remaining = [v for v in self.versions_dir.iterdir() if v.is_dir()]
        if len(remaining) > self.max_versions:
            # 找出最旧的非当前版本
            remaining.sort(key=lambda p: p.name, reverse=True)
            for old in reversed(remaining):
                if old.name != current:
                    try:
                        shutil.rmtree(old)
                        deleted.append(old.name)
                    except Exception as e:
                        print(f"[IndexVersionManager] 清理旧版本失败 {old.name}: {e}")
                    break

        return deleted

    def delete_version(self, version_id: str) -> bool:
        """删除指定版本（不能删除当前激活版本）"""
        current = self.get_current_version()
        if version_id == current:
            raise ValueError("不能删除当前激活的版本")

        version_path = self.get_version_path(version_id)
        if version_path.exists():
            shutil.rmtree(version_path)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """获取版本管理器状态"""
        versions = self.list_versions()
        return {
            "current_version": self.get_current_version(),
            "total_versions": len(versions),
            "max_versions": self.max_versions,
            "versions_dir": str(self.versions_dir),
        }
