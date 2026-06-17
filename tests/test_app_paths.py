from src.utils import app_paths


def test_server_mode_uses_project_data(monkeypatch):
    monkeypatch.delenv("SECONDBRAIN_DESKTOP_MODE", raising=False)
    monkeypatch.delenv("SECONDBRAIN_USER_DATA_DIR", raising=False)

    paths = app_paths.get_app_paths()

    assert paths.user_data_dir == app_paths.project_root() / "data"
    assert paths.conversations_db == app_paths.project_root() / "data" / "conversations.db"


def test_desktop_mode_uses_user_data_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    paths = app_paths.get_app_paths()

    assert paths.user_data_dir == tmp_path
    assert paths.index_dir == tmp_path / "index"
    assert paths.model_config_file == tmp_path / "config" / "model_config.json"


def test_ensure_app_dirs_creates_required_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    paths = app_paths.ensure_app_dirs()

    assert paths.config_dir.is_dir()
    assert paths.index_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.models_dir.is_dir()
