from uuid import uuid4

from test_chat import chat  # noqa: F401
from test_reading import reading  # noqa: F401


def plan():
    return {
        "name": "Sites",
        "granularity": "每个站点一行",
        "record_key": ["site"],
        "fields": [{"key": "site", "label": "站点", "type": "string"}],
    }


def test_fulltext_plan_design_requires_explicit_batch(chat):  # noqa: F811
    from pathlib import Path

    from backend.parsing_next.bundle import Bundle, write_json

    client, answer_path, model, project_path, file = chat
    project_id = project_path.split("/")[-1]
    asset = client.get(project_path + "/documents").json()[0]["assets"][0]
    folder = client.app.state.full_document.folder(project_id, asset["id"])
    bundle = Bundle(folder / "fixture", Path(file), "fixture")
    bundle.add("source " * 10000)
    bundle.finish(engine="fixture", source_sha256=asset["sha256"])
    write_json(folder / "active.json", {"version": "fixture", "source_sha256": asset["sha256"]})
    calls = []
    model.complete = lambda *args: calls.append(args) or plan()
    path = answer_path.removesuffix("/answers") + "/plans"
    body = {"goal": "提取站点", "document_ids": []}
    assert client.post(path, json=body, headers={"X-Model-Key": "test"}).status_code == 400
    assert not calls
    response = client.post(
        path, json={**body, "fulltext_batch": 2}, headers={"X-Model-Key": "test"}
    )
    assert response.status_code == 200, response.text
    assert "2/2" in response.json()["goal"] and len(calls) == 1


def test_confirm_versions_scope_cancel_recovery_and_events(chat):  # noqa: F811
    client, answer_path, model, project_path, file = chat
    jobs_service = client.app.state.jobs
    jobs_service.close()  # Deterministic durable queue test; desktop E2E executes real workers.
    model.complete = lambda *args: plan()
    base = answer_path.removesuffix("/answers")
    draft = client.post(
        base + "/plans",
        json={"goal": "提取站点", "document_ids": []},
        headers={"X-Model-Key": "test"},
    ).json()
    assert draft["status"] == "draft"
    assert client.get(base + "/jobs").json() == []
    request = {"schema_id": draft["id"], "request_id": str(uuid4()), "plan": plan()}
    job = client.post(base + "/jobs", json=request, headers={"X-Model-Key": "test"}).json()
    assert job["status"] == "pending"
    assert (
        client.post(base + "/jobs", json=request, headers={"X-Model-Key": "test"}).json()["id"]
        == job["id"]
    )
    path = project_path + f"/jobs/{job['id']}"
    detail = client.get(path).json()
    assert detail["schema"]["version"] > draft["version"]
    assert client.get(path.replace(project_path.split("/")[-1], str(uuid4()))).status_code == 404
    assert client.post(path + "/cancel").json()["status"] == "cancelled"
    events = client.get(path + "/events")
    assert events.headers["content-type"].startswith("text/event-stream")
    assert '"status": "cancelled"' in events.text
    assert (
        client.post(path + "/resume", headers={"X-Model-Key": "test"}).json()["status"] == "pending"
    )
    jobs_service.repository.recover()
    assert client.get(path).json()["status"] == "interrupted"
    assert client.get(path + "/records").json() == []
