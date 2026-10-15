from uuid import uuid4

from test_chat import chat  # noqa: F401
from test_reading import reading  # noqa: F401


def test_plugin_switches_are_scoped_and_schema_pins_survive_disabling(chat):  # noqa: F811
    client, answer_path, _, project_path, _ = chat
    base = answer_path.removesuffix("/answers")
    initial = client.get(project_path + "/plugins").json()
    assert initial[0]["enabled"] is False
    assert client.post(base + "/templates", json={"plugin_id": "microplastics"}).status_code == 400
    assert (
        client.put(project_path + "/plugins/microplastics", json={"enabled": True}).status_code
        == 200
    )
    draft = client.post(base + "/templates", json={"plugin_id": "microplastics"}).json()
    assert draft["plan"]["plugins"] == [{"id": "microplastics", "version": "1.0.0"}]
    assert client.get(base + "/jobs").json() == []
    assert (
        client.put(project_path + "/plugins/microplastics", json={"enabled": False}).status_code
        == 200
    )
    assert client.get(base + "/plans").json()[0]["plan"]["plugins"] == draft["plan"]["plugins"]
    assert (
        client.get(
            project_path.replace(project_path.split("/")[-1], str(uuid4())) + "/plugins"
        ).status_code
        == 404
    )
