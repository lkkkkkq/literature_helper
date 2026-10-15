import time
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.core.documents import DocumentBlock, ParsedContent
from backend.main import create_app
from backend.parsers.docling_adapter import DoclingAdapter
from scripts.create_reading_fixtures import create_fixtures


class ControlledParser:
    version = "test-1"

    def __init__(self):
        self.calls = 0
        self.release = Event()
        self.release.set()
        self.fail = False

    def parse(self, data, asset, ocr):
        self.calls += 1
        assert self.release.wait(10)
        if self.fail:
            raise ValueError("broken document")
        return ParsedContent(
            parser_version=self.version,
            source_sha256=asset["sha256"],
            asset_id=asset["id"],
            filename=asset["relative_path"],
            blocks=[DocumentBlock(id="one", kind="text", text="Alpha", label="text")],
        )


@pytest.fixture
def reading(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    file = source / "paper.pdf"
    file.write_bytes(b"test source")
    app = create_app(Settings(tmp_path / "data", "test"))
    with TestClient(app, headers={"Authorization": "Bearer test"}) as client:
        parser = ControlledParser()
        app.state.reading.parser = parser
        project = client.post(
            "/api/projects", json={"name": "Reading", "source_path": str(source)}
        ).json()
        project_path = f"/api/projects/{project['id']}"
        draft = client.post(project_path + "/scan").json()
        result = client.post(
            project_path + "/scan/confirm",
            json={
                "draft_id": draft["id"],
                "groups": [
                    {key: group[key] for key in ["title", "main_path", "asset_paths"]}
                    for group in draft["snapshot"]["groups"]
                ],
            },
        ).json()
        path = project_path + f"/assets/{result[0]['assets'][0]['id']}"
        yield client, app, parser, path, file
        parser.release.set()
        app.state.reading.executor.shutdown(wait=True)


def wait_finished(client, path):
    for _ in range(200):
        state = client.get(path + "/parse").json()
        if state["status"] not in {"queued", "running"}:
            return state
        time.sleep(0.01)
    pytest.fail("Parse did not finish")


def test_parse_cache_and_source_fingerprint(reading):
    client, app, parser, path, file = reading
    assert client.get(path + "/content").status_code == 409
    assert client.get(path + "/pdf").content == b"test source"
    assert client.post(path + "/parse", json={}).status_code == 202
    first = wait_finished(client, path)
    assert first["status"] == "ready"
    assert "result_path" not in first
    assert client.get(path + "/content").json()["blocks"][0]["text"] == "Alpha"
    assert client.post(path + "/parse", json={}).json()["run_id"] == first["run_id"]
    assert parser.calls == 1
    assert client.post(path + "/parse", json={"force": True}).status_code == 202
    assert wait_finished(client, path)["run_id"] != first["run_id"]
    file.write_bytes(b"changed source")
    for suffix in ["/content", "/pdf"]:
        assert client.get(path + suffix).status_code == 409
    assert client.post(path + "/parse", json={}).status_code == 409


def test_duplicate_requests_and_change_during_parse(reading):
    client, app, parser, path, file = reading
    parser.release.clear()
    first = client.post(path + "/parse", json={}).json()
    second = client.post(path + "/parse", json={"force": True}).json()
    assert first["run_id"] == second["run_id"]
    file.write_bytes(b"changed during parsing")
    parser.release.set()
    assert wait_finished(client, path)["status"] == "failed"
    assert client.get(path + "/content").status_code == 409
    assert list(app.state.reading.data_dir.glob("projects/*/parsed/*/*.json")) == []


def test_failure_retry_cache_corruption_and_scope(reading):
    client, app, parser, path, file = reading
    wrong = path.replace(path.split("/")[3], "other-project")
    for suffix in ["/parse", "/content", "/pdf"]:
        assert client.get(wrong + suffix).status_code == 404
    assert client.post(wrong + "/parse", json={}).status_code == 404
    parser.fail = True
    client.post(path + "/parse", json={})
    assert wait_finished(client, path)["status"] == "failed"
    parser.fail = False
    client.post(path + "/parse", json={})
    assert wait_finished(client, path)["status"] == "ready"


def test_real_parser_runs_in_background(reading, tmp_path):
    client, app, parser, path, file = reading
    create_fixtures(tmp_path / "fixtures")
    # Replace the indexed bytes via a fresh scan, as the UI requires.
    file.write_bytes((tmp_path / "fixtures/paper.pdf").read_bytes())
    project_path = path.split("/assets/")[0]
    draft = client.post(project_path + "/scan").json()
    response = client.post(
        project_path + "/scan/confirm",
        json={
            "draft_id": draft["id"],
            "groups": [
                {key: group[key] for key in ["title", "main_path", "asset_paths"]}
                for group in draft["snapshot"]["groups"]
            ],
        },
    )
    assert response.status_code == 200
    app.state.reading.parser = DoclingAdapter(Path(".local/docling-models"))
    assert client.post(path + "/parse", json={}).status_code == 202
    for _ in range(600):
        state = client.get(path + "/parse").json()
        if state["status"] not in {"queued", "running"}:
            break
        time.sleep(0.1)
    assert state["status"] == "ready", state
    assert "observed concentration" in client.get(path + "/content").text
    cache = next(app.state.reading.data_dir.glob("projects/*/parsed/*/*.json"))
    cache.write_text("{}", encoding="utf-8")
    assert client.get(path + "/content").status_code == 400


def test_interrupted_recovery(reading):
    client, app, parser, path, file = reading
    repository = app.state.reading.repository
    parts = path.split("/")
    asset = repository.asset(parts[3], parts[5])
    run, claimed = repository.claim(asset, parser.version, False, False)
    assert claimed
    repository.mark_running(run["run_id"])
    repository.recover()
    assert client.get(path + "/parse").json()["status"] == "interrupted"
    client.post(path + "/parse", json={})
    assert wait_finished(client, path)["status"] == "ready"
