from app.config import load_settings


def test_base_url_defaults_when_env_is_empty(monkeypatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "")
    assert load_settings().opencode_base_url == "https://opencode.ai/zen/go/v1"


def test_base_url_defaults_when_env_is_missing(monkeypatch):
    monkeypatch.delenv("OPENCODE_BASE_URL", raising=False)
    assert load_settings().opencode_base_url == "https://opencode.ai/zen/go/v1"


def test_base_url_is_trimmed(monkeypatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "  https://example.com/v1  ")
    assert load_settings().opencode_base_url == "https://example.com/v1"
