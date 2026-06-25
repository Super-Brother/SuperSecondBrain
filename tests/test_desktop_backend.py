import importlib

from src import desktop_backend


def test_initialize_desktop_runtime_imports_torch(monkeypatch):
    imported = []
    monkeypatch.setattr(importlib, "import_module", imported.append)

    desktop_backend.initialize_desktop_runtime()

    assert imported == ["torch"]
