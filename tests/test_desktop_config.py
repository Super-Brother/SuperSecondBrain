from src.utils.desktop_config import DesktopConfig, load_desktop_config, save_desktop_config


def test_load_missing_config_returns_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    cfg = load_desktop_config()

    assert cfg.vault_path == ""
    assert cfg.llm_base_url == "http://localhost:11434/v1"
    assert cfg.onboarding_complete is False


def test_save_and_load_desktop_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SECONDBRAIN_DESKTOP_MODE", "1")
    monkeypatch.setenv("SECONDBRAIN_USER_DATA_DIR", str(tmp_path))

    save_desktop_config(DesktopConfig(
        vault_path="/tmp/vault",
        llm_base_url="http://localhost:11434/v1",
        llm_api_key="not-needed",
        llm_model="qwen2.5:7b",
        onboarding_complete=True,
    ))

    cfg = load_desktop_config()

    assert cfg.vault_path == "/tmp/vault"
    assert cfg.llm_model == "qwen2.5:7b"
    assert cfg.onboarding_complete is True
