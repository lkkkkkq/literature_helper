import pytest

from backend.core.config import Settings


def test_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("LITEXTRACT_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="LITEXTRACT_API_TOKEN"):
        Settings.from_env()


def test_environment_paths_are_resolved(monkeypatch, tmp_path):
    monkeypatch.setenv("LITEXTRACT_API_TOKEN", "test-only")
    monkeypatch.setenv("LITEXTRACT_DATA_DIR", str(tmp_path))
    settings = Settings.from_env()
    assert settings.data_dir == tmp_path.resolve()
