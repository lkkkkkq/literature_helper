import json
from uuid import uuid4

import pytest
from test_reading import reading, wait_finished  # noqa: F401

from backend.core.chat import ModelProfileInput


class Model:
    def __init__(self):
        self.calls = []
        self.invalid = False

    def complete(self, profile, key, messages):
        payload = json.loads(messages[-1]["content"])
        self.calls.append(payload)
        return {
            "parts": [
                {
                    "text": "研究样本为 Alpha。",
                    "evidence_ids": ["invented" if self.invalid else payload["sources"][0]["id"]],
                    "kind": "claim",
                }
            ]
        }


@pytest.fixture
def chat(reading):  # noqa: F811
    client, app, parser, asset_path, file = reading
    project_path = asset_path.split("/assets/")[0]
    conversation = client.post(project_path + "/sessions", json={}).json()
    path = project_path + f"/sessions/{conversation['id']}/answers"
    client.post(asset_path + "/parse", json={})
    assert wait_finished(client, asset_path)["status"] == "ready"
    model = Model()
    app.state.chat.model = model
    assert (
        client.put(
            project_path + "/model",
            json={"base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
        ).status_code
        == 200
    )
    return client, path, model, project_path, file


def question():
    return {
        "question": "请说明研究问题、方法、结果和局限",
        "request_id": str(uuid4()),
        "document_ids": [],
    }


def test_qa_citations_history_scope_and_idempotency(chat):
    client, path, model, project_path, file = chat
    body = question()
    response = client.post(path, json=body, headers={"X-Model-Key": "test-only"})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "complete"
    assert run["answer"]["evidence"][0]["quote"] == "Alpha"
    assert "提取方案" not in run["answer"]["parts"][0]["text"]
    assert len(model.calls) == 1
    assert (
        client.post(path, json=body, headers={"X-Model-Key": "test-only"}).json()["id"] == run["id"]
    )
    assert len(model.calls) == 1
    second = client.post(project_path + "/sessions", json={}).json()
    assert client.get(project_path + f"/sessions/{second['id']}/answers").json() == []
    assert client.get(path.replace(project_path.split("/")[-1], str(uuid4()))).status_code == 404
    assert (
        client.post(
            path,
            json={**question(), "document_ids": [str(uuid4())]},
            headers={"X-Model-Key": "test-only"},
        ).status_code
        == 404
    )


def test_qa_rejects_missing_key_invalid_evidence_and_changed_source(chat):
    client, path, model, project_path, file = chat
    assert client.post(path, json=question()).status_code == 400
    model.invalid = True
    result = client.post(path, json=question(), headers={"X-Model-Key": "test-only"}).json()
    assert result["status"] == "failed"
    assert result["answer"] is None
    file.write_bytes(b"changed")
    assert (
        client.post(path, json=question(), headers={"X-Model-Key": "test-only"}).status_code == 409
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.test",
        "https://user:key@remote.test",
        "https://remote.test?key=secret",
        "file:///tmp/key",
    ],
)
def test_model_profile_rejects_unsafe_addresses(url):
    with pytest.raises(ValueError):
        ModelProfileInput(base_url=url, model="model")
