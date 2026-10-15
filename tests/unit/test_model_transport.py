import json

import httpx
import pytest

from backend.agent.model_adapter import CompatibleModel
from backend.core.errors import DomainError


@pytest.mark.parametrize(
    "base,model,thinking",
    [
        ("https://api.deepseek.com", "deepseek-flash", True),
        ("https://api.deepseek.com/v1", "deepseek-v4-pro", True),
        ("https://example.com", "deepseek-flash", False),
        ("https://api.deepseek.com.example.com", "deepseek-flash", False),
    ],
)
def test_provider_options(monkeypatch, base, model, thinking):
    original = httpx.Client

    def handle(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == (65536 if thinking else 8192)
        assert ("thinking" in payload) == thinking
        if thinking:
            assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"records": []}'}}]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    assert CompatibleModel().complete({"base_url": base, "model": model}, "test-key", []) == {
        "records": []
    }


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("length", "finish_reason=length"),
        ("content_filter", "content_filter"),
        ("insufficient_system_resource", "资源不足"),
        (None, "接口兼容性"),
    ],
)
def test_incomplete_results_are_rejected(monkeypatch, reason, expected):
    original = httpx.Client
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": reason, "message": {"content": '{"records": []}'}}]
            },
        )

    transport = httpx.MockTransport(reply)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(DomainError, match=expected):
        CompatibleModel().complete(
            {"base_url": "https://api.deepseek.com", "model": "deepseek-flash"}, "test-key", []
        )
    assert len(calls) == 1


def test_large_deepseek_result_exceeds_old_body_limit(monkeypatch):
    original = httpx.Client
    content = {"text": "A" * 2_100_000}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]
            },
        )
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    assert (
        CompatibleModel().complete(
            {"base_url": "https://api.deepseek.com", "model": "deepseek-flash"}, "test-key", []
        )
        == content
    )
