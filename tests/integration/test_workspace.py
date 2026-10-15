import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "中文 论文"
    source.mkdir()
    settings = Settings(tmp_path / "data", "test-secret")
    with TestClient(
        create_app(settings), headers={"Authorization": "Bearer test-secret"}
    ) as client:
        yield client, source, settings


def create(client, source, name="文献项目"):
    response = client.post("/api/projects", json={"name": name, "source_path": str(source)})
    assert response.status_code == 201, response.text
    return response.json()


def add_file(source, path, content=b"fixture-not-a-real-paper"):
    file = source / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return file


def preview(client, project):
    response = client.post(f"/api/projects/{project['id']}/scan")
    assert response.status_code == 200, response.text
    return response.json()


def body(draft):
    return {
        "draft_id": draft["id"],
        "groups": [
            {key: group[key] for key in ["title", "main_path", "asset_paths"]}
            for group in draft["snapshot"]["groups"]
        ],
    }


def confirm(client, project, draft):
    response = client.post(f"/api/projects/{project['id']}/scan/confirm", json=body(draft))
    assert response.status_code == 200, response.text
    return response.json()


def test_projects_sessions_survive_restart_without_overwrite(workspace):
    client, source, settings = workspace
    first, second = create(client, source), create(client, source)
    assert first["id"] != second["id"]
    path = f"/api/projects/{first['id']}"
    one = client.post(path + "/sessions", json={"name": "会话一"}).json()
    two = client.post(path + "/sessions", json={"name": "会话二"}).json()
    assert one["id"] != two["id"]
    client.post(path + f"/sessions/{one['id']}/messages", json={"content": "只属于会话一"})
    assert client.patch(path, json={"name": "新标题"}).json()["name"] == "新标题"
    with TestClient(create_app(settings), headers=client.headers) as restarted:
        projects = restarted.get("/api/projects").json()
        assert len(projects) == 2
        assert restarted.get(path).json()["name"] == "新标题"
        assert len(restarted.get(path + "/sessions").json()) == 2
        assert restarted.get(path + f"/sessions/{two['id']}/messages").json() == []
        notes = restarted.get(path + f"/sessions/{one['id']}/messages").json()
        assert notes[0]["content"] == "只属于会话一"
        assert notes[0]["role"] == "note"


def test_cross_project_operations_are_rejected(workspace):
    client, source, _ = workspace
    add_file(source, "paper.pdf")
    first, second = create(client, source), create(client, source)
    first_path = f"/api/projects/{first['id']}"
    second_path = f"/api/projects/{second['id']}"
    session = client.post(first_path + "/sessions", json={}).json()
    wrong = second_path + f"/sessions/{session['id']}"
    assert client.get(wrong + "/messages").status_code == 404
    assert client.post(wrong + "/messages", json={"content": "错误写入"}).status_code == 404
    assert client.patch(wrong, json={"name": "错误改名"}).status_code == 404
    assert client.delete(wrong).status_code == 404
    documents = confirm(client, first, preview(client, first))
    assert client.get(second_path + f"/documents/{documents[0]['id']}").status_code == 404
    assert client.get(second_path + "/documents").json() == []


def test_preview_persists_and_scan_is_read_only(workspace):
    client, source, settings = workspace
    files = [
        add_file(source, "study/paper.pdf"),
        add_file(source, "study/Supplement.csv"),
        add_file(source, "study/tables/detail.xlsx"),
        add_file(source, "alone.csv"),
    ]
    before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    project = create(client, source)
    draft = preview(client, project)
    assert len(draft["snapshot"]["assets"]) == 4
    assert len(draft["snapshot"]["groups"]) == 2
    assert any(group["confidence"] == "review" for group in draft["snapshot"]["groups"])
    assert client.get(f"/api/projects/{project['id']}/documents").json() == []
    with TestClient(create_app(settings), headers=client.headers) as restarted:
        recovered = restarted.get(f"/api/projects/{project['id']}/scan").json()
        assert recovered["id"] == draft["id"]
        documents = confirm(restarted, project, recovered)
        assert len(documents) == 2
    for path in files:
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before[str(path)]
    assets = [asset for document in documents for asset in document["assets"]]
    assert {asset["sha256"] for asset in assets} == {
        hashlib.sha256(files[0].read_bytes()).hexdigest()
    }


def test_rescan_preserves_ids_marks_changes_and_missing(workspace):
    client, source, _ = workspace
    paper = add_file(source, "paper.pdf", b"first")
    appendix = add_file(source, "paper_supp.csv", b"table")
    project = create(client, source)
    first = confirm(client, project, preview(client, project))
    first_id = first[0]["id"]
    old_assets = {asset["relative_path"]: asset["id"] for asset in first[0]["assets"]}
    repeated = confirm(client, project, preview(client, project))
    assert repeated[0]["id"] == first_id
    assert len(repeated) == 1
    paper.write_bytes(b"second")
    appendix.unlink()
    add_file(source, "paper_extra.xlsx")
    rescanned = confirm(client, project, preview(client, project))
    assets = {asset["relative_path"]: asset for asset in rescanned[0]["assets"]}
    assert rescanned[0]["id"] == first_id
    assert assets["paper.pdf"]["status"] == "changed"
    assert assets["paper.pdf"]["id"] == old_assets["paper.pdf"]
    assert assets["paper_supp.csv"]["status"] == "missing"
    assert assets["paper_extra.xlsx"]["status"] == "active"


def test_manual_grouping_is_retained_on_rescan(workspace):
    client, source, _ = workspace
    add_file(source, "one.pdf")
    add_file(source, "two.pdf")
    project = create(client, source)
    draft = preview(client, project)
    payload = {
        "draft_id": draft["id"],
        "groups": [
            {"title": "手动研究名称", "main_path": "one.pdf", "asset_paths": ["one.pdf", "two.pdf"]}
        ],
    }
    path = f"/api/projects/{project['id']}/scan/confirm"
    assert client.post(path, json=payload).status_code == 200
    repeated = preview(client, project)["snapshot"]["groups"]
    assert len(repeated) == 1
    assert repeated[0]["title"] == "手动研究名称"
    assert set(repeated[0]["asset_paths"]) == {"one.pdf", "two.pdf"}


def test_changed_files_and_stale_previews_cannot_be_committed(workspace):
    client, source, _ = workspace
    file = add_file(source, "paper.pdf")
    project = create(client, source)
    old = preview(client, project)
    latest = preview(client, project)
    path = f"/api/projects/{project['id']}/scan/confirm"
    assert client.post(path, json=body(old)).status_code == 409
    file.write_bytes(b"changed-after-preview")
    assert client.post(path, json=body(latest)).status_code == 409
    assert client.get(f"/api/projects/{project['id']}/documents").json() == []
    current = preview(client, project)
    confirm(client, project, current)
    assert client.post(path, json=body(current)).status_code == 409


@pytest.mark.parametrize("bad", ["duplicate", "outside", "missing", "wrong_main"])
def test_confirm_validates_full_partition(workspace, bad):
    client, source, _ = workspace
    add_file(source, "paper.pdf")
    project = create(client, source)
    payload = body(preview(client, project))
    if bad == "duplicate":
        payload["groups"].append(payload["groups"][0])
    elif bad == "outside":
        payload["groups"][0]["asset_paths"].append("../outside.pdf")
    elif bad == "missing":
        payload["groups"] = []
    else:
        payload["groups"][0]["main_path"] = "other.pdf"
    assert (
        client.post(f"/api/projects/{project['id']}/scan/confirm", json=payload).status_code == 400
    )


def test_delete_cascades_metadata_but_preserves_sources_and_other_projects(workspace):
    client, source, settings = workspace
    file = add_file(source, "paper.pdf")
    original = file.read_bytes()
    first, second = create(client, source), create(client, source)
    path = f"/api/projects/{first['id']}"
    confirm(client, first, preview(client, first))
    preview(client, first)
    session = client.post(path + "/sessions", json={}).json()
    client.post(path + f"/sessions/{session['id']}/messages", json={"content": "笔记"})
    assert client.delete(path).status_code == 204
    assert client.get(f"/api/projects/{second['id']}").status_code == 200
    assert file.read_bytes() == original
    with sqlite3.connect(settings.data_dir / "workspace.db") as connection:
        for table in ["documents", "document_assets", "chat_sessions", "messages", "scan_drafts"]:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_session_rename_delete_and_empty_input(workspace):
    client, source, _ = workspace
    project = create(client, source)
    path = f"/api/projects/{project['id']}/sessions"
    assert client.post(path, json={"name": "  "}).status_code == 422
    session = client.post(path, json={"name": " reading "}).json()
    assert session["name"] == "reading"
    url = path + f"/{session['id']}"
    assert client.patch(url, json={"name": " renamed "}).json()["name"] == "renamed"
    assert client.post(url + "/messages", json={"content": "  "}).status_code == 422
    assert (
        client.post(url + "/messages", json={"content": "ok", "role": "assistant"}).status_code
        == 422
    )
    assert client.post(url + "/messages", json={"content": "note"}).status_code == 201
    assert client.delete(url).status_code == 204
    assert client.get(url + "/messages").status_code == 404


def test_invalid_source_and_failed_rescan_preserve_index(workspace):
    client, source, settings = workspace
    assert (
        client.post("/api/projects", json={"name": " ", "source_path": str(source)}).status_code
        == 422
    )
    assert (
        client.post("/api/projects", json={"name": "bad", "source_path": "relative"}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/projects", json={"name": "bad", "source_path": str(settings.data_dir)}
        ).status_code
        == 400
    )
    add_file(source, "paper.pdf")
    project = create(client, source)
    before = confirm(client, project, preview(client, project))
    source.rename(source.with_name("temporarily-moved"))
    assert client.post(f"/api/projects/{project['id']}/scan").status_code == 400
    assert client.get(f"/api/projects/{project['id']}/documents").json() == before


def test_read_failure_does_not_replace_preview(workspace, monkeypatch):
    client, source, _ = workspace
    file = add_file(source, "paper.pdf")
    project = create(client, source)
    draft = preview(client, project)
    original = Path.open

    def blocked(self, *args, **kwargs):
        if self == file:
            raise PermissionError("test denial")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", blocked)
    assert client.post(f"/api/projects/{project['id']}/scan").status_code == 400
    assert client.get(f"/api/projects/{project['id']}/scan").json()["id"] == draft["id"]


def test_concurrent_project_creation_never_overwrites(workspace):
    client, source, _ = workspace
    with ThreadPoolExecutor(max_workers=4) as executor:
        projects = list(executor.map(lambda _: create(client, source, "同名项目"), range(8)))
    assert len({project["id"] for project in projects}) == 8
    assert len(client.get("/api/projects").json()) == 8
