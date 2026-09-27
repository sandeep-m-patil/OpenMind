"""HTTP clients (Gemini, Groq, Hindsight, Prometheus, health) against mocked transports."""
import json

import httpx
import pytest

from app.config import load_settings
from app.services.llm import GeminiProvider, GroqProvider, LLMError, LLMRateLimited, build_llm
from app.services.memory import MemoryItem, MemoryService, MemoryUnavailable
from app.tools.health import check_health
from app.tools.metrics import PrometheusClient


def _transport(status: int, body, seen: list | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body)

    return httpx.MockTransport(handle)


def test_gemini_sends_key_in_header_not_url():
    seen = []
    body = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
    GeminiProvider("secret", "m", _transport(200, body, seen)).complete_json("s", "u")

    assert (seen[0].headers["x-goog-api-key"], "secret" in str(seen[0].url)) == ("secret", False)


def test_gemini_rate_limit_is_distinguished():
    with pytest.raises(LLMRateLimited):
        GeminiProvider("k", "m", _transport(429, {})).complete_json("s", "u")


def test_gemini_without_text_is_an_error():
    with pytest.raises(LLMError):
        GeminiProvider("k", "m", _transport(200, {"candidates": []})).complete_json("s", "u")


def test_groq_requests_json_mode():
    seen = []
    GroqProvider("k", "m", _transport(200, {"choices": [{"message": {"content": "{}"}}]}, seen)).complete_json("s", "u")

    assert json.loads(seen[0].content)["response_format"] == {"type": "json_object"}


def test_groq_server_error_is_an_error():
    with pytest.raises(LLMError):
        GroqProvider("k", "m", _transport(500, "oops")).complete_json("s", "u")


def test_llm_chain_uses_only_configured_providers(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "g")

    assert build_llm(load_settings())._providers[0].name == "groq"


def test_retain_posts_items_with_string_metadata():
    seen = []
    memory = MemoryService("http://h", "bank", _transport(200, {"success": True}, seen))
    memory.retain([MemoryItem("text", "ctx", "INC-1", metadata={"p95": 1.5}, tags=["service:x"])])

    body = json.loads(seen[0].content)
    assert (seen[0].url.path, body["items"][0]["metadata"]) == ("/v1/default/banks/bank/memories", {"p95": "1.5"})


def test_recall_filters_by_service_tag_and_parses_results():
    seen = []
    result = {"results": [{"id": "1", "text": "t", "scores": {"final": 0.9}, "document_id": "INC-1", "metadata": {"a": "b"}}]}
    memories = MemoryService("http://h", "bank", _transport(200, result, seen)).recall("q", tags=["service:x"])

    assert (json.loads(seen[0].content)["tags_match"], memories[0].score, memories[0].document_id) == ("any_strict", 0.9, "INC-1")


def test_recall_on_empty_bank_returns_nothing():
    assert MemoryService("http://h", "bank", _transport(404, {})).recall("q") == []


def test_hindsight_errors_raise_memory_unavailable():
    with pytest.raises(MemoryUnavailable):
        MemoryService("http://h", "bank", _transport(500, "down")).retain([MemoryItem("t", "c", "d")])


def test_unreachable_hindsight_raises_memory_unavailable():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(MemoryUnavailable):
        MemoryService("http://h", "bank", httpx.MockTransport(refuse)).recall("q")


def test_prometheus_scalar_and_missing_data():
    ok = {"status": "success", "data": {"result": [{"value": [0, "0.25"]}]}}
    empty = {"status": "success", "data": {"result": []}}

    assert (PrometheusClient("http://p", _transport(200, ok)).query_scalar("x"),
            PrometheusClient("http://p", _transport(200, empty)).query_scalar("x")) == (0.25, None)


def test_prometheus_nan_is_treated_as_no_data():
    nan = {"status": "success", "data": {"result": [{"value": [0, "NaN"]}]}}

    assert PrometheusClient("http://p", _transport(200, nan)).snapshot()["p95_seconds"] is None


def test_prometheus_error_status_raises():
    with pytest.raises(RuntimeError):
        PrometheusClient("http://p", _transport(200, {"status": "error", "error": "bad"})).query_scalar("x")


def test_health_tool_reads_the_envelope():
    body = {"data": {"status": "degraded", "components": {"redis": "down"}}}

    assert check_health("http://s", _transport(503, body))["status"] == "degraded"
