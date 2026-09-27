import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import build_env

FIRING = {"status": "firing", "alerts": [
    {"status": "firing", "labels": {"alertname": "HighLatency", "severity": "critical", "service": "product-api"},
     "annotations": {"summary": "product-api P95 latency above 1s"}},
    {"status": "firing", "labels": {"alertname": "CacheSaturation", "severity": "warning", "service": "product-api"},
     "annotations": {}},
]}


@pytest.fixture
def api():
    env = build_env()
    with TestClient(create_app(lambda settings: env)) as client:
        client.env = env
        yield client


def _open(api) -> str:
    return api.post("/v1/alerts/prometheus", json=FIRING).json()["data"]["opened"][0]


def test_critical_alert_opens_incident_and_warning_is_ignored(api):
    data = api.post("/v1/alerts/prometheus", json=FIRING).json()["data"]

    assert (len(data["opened"]), data["ignored"]) == (1, 1)


def test_repeat_alert_is_absorbed_by_open_incident(api):
    first = _open(api)

    assert api.post("/v1/alerts/prometheus", json=FIRING).json()["data"]["absorbed"] == [first]


def test_incident_detail_includes_full_state(api):
    body = api.get(f"/v1/incidents/{_open(api)}").json()["data"]

    assert (body["status"], body["recommended_runbook"], "trace" in body["state"]) == ("PENDING_APPROVAL", "RB-CACHE-002", True)


def test_list_is_newest_first_with_cursor(api):
    first = _open(api)
    api.post(f"/v1/incidents/{first}/decisions", json={"decision": "REJECTED", "operator": "sre"})
    second = api.post("/v1/incidents", json={"title": "Manual check"}).json()["data"]["id"]

    page = api.get("/v1/incidents", params={"limit": 1}).json()

    assert (page["data"][0]["id"], page["meta"]["next_cursor"]) == (second, second)


def test_decision_endpoint_runs_the_rest_of_the_workflow(api):
    incident_id = _open(api)

    response = api.post(f"/v1/incidents/{incident_id}/decisions", json={
        "decision": "MODIFIED", "operator": "sre", "runbook_id": "RB-CACHE-001", "comment": "stale only"})

    assert (response.status_code, api.get(f"/v1/incidents/{incident_id}").json()["data"]["status"]) == (202, "RESOLVED")


def test_decision_conflict_returns_409(api):
    incident_id = _open(api)
    api.post(f"/v1/incidents/{incident_id}/decisions", json={"decision": "REJECTED", "operator": "a"})

    assert api.post(f"/v1/incidents/{incident_id}/decisions", json={"decision": "APPROVED", "operator": "b"}).status_code == 409


def test_policy_violation_returns_422(api):
    incident_id = _open(api)

    response = api.post(f"/v1/incidents/{incident_id}/decisions", json={
        "decision": "MODIFIED", "operator": "sre", "runbook_id": "RB-CACHE-001", "params": {"max_idle_hours": -1}})

    assert (response.status_code, "outside" in response.json()["error"]["message"]) == (422, True)


def test_unknown_incident_is_404(api):
    assert api.get("/v1/incidents/INC-4242").status_code == 404


def test_decision_for_unknown_incident_is_404(api):
    assert api.post("/v1/incidents/INC-4242/decisions", json={"decision": "APPROVED", "operator": "a"}).status_code == 404


def test_invalid_payload_uses_error_envelope(api):
    body = api.post("/v1/incidents/INC-1/decisions", json={"decision": "YOLO", "operator": "a"}).json()

    assert (body["data"], body["error"]["message"]) == (None, "invalid request")


def test_runbooks_and_strategies_are_listed(api):
    _open(api)

    assert (len(api.get("/v1/runbooks").json()["data"]), api.get("/v1/strategies").json()["data"]) == (4, [])


def test_memory_search_passes_through_to_hindsight(api):
    incident_id = _open(api)
    api.post(f"/v1/incidents/{incident_id}/decisions", json={"decision": "APPROVED", "operator": "a"})

    memories = api.get("/v1/memories", params={"query": "cache", "service": "product-api"}).json()["data"]

    assert memories[0]["document_id"] == incident_id


def test_memory_search_reports_hindsight_outage(api):
    api.env.memory.is_up = False

    assert api.get("/v1/memories", params={"query": "cache"}).status_code == 503


def test_deployments_can_be_recorded_and_listed(api):
    api.post("/v1/deployments", json={"service": "product-api", "version": "v1.2.3"})

    assert api.get("/v1/deployments").json()["data"][-1]["version"] == "v1.2.3"


def test_health_reports_components(api):
    components = api.get("/health").json()["data"]["components"]

    assert (components["prometheus"], components["llm"]) == ("up", "not configured (rule engine)")
