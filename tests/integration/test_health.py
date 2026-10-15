from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app

TOKEN = "integration-test-token"


def test_authentication_and_readiness(tmp_path):
    with TestClient(create_app(Settings(tmp_path, TOKEN))) as client:
        assert client.get("/api/health").status_code == 401
        assert (
            client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )
        response = client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200
        assert response.json()["database"] == "wal"
        assert response.json()["migration"] == "0007_plugins"
    assert (tmp_path / "workspace.db").is_file()


def test_migrations_are_restart_safe_and_workspaces_isolated(tmp_path):
    for name in ["first", "second", "first"]:
        folder = tmp_path / name
        with TestClient(create_app(Settings(folder, TOKEN))) as client:
            assert (
                client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"}).status_code
                == 200
            )
    assert (tmp_path / "first/workspace.db").is_file()
    assert (tmp_path / "second/workspace.db").is_file()
