"""Integration tests against the real PostgreSQL from `docker compose up` (database opsmind_test).

Set TEST_DATABASE_URL, e.g. postgresql://opsmind:<password>@127.0.0.1:5433/opsmind_test
Skipped otherwise, so the unit suite still runs without Docker.
"""
import os

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from app.db import apply_schema, ensure_database, open_pool
from app.schemas.deployments import DeploymentIn
from app.services.deployment_store import DeploymentStore
from app.services.incident_store import IncidentStore
from app.services.strategy_scores import StrategyScores

DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Skipped (not failed) without a running stack: these need a real PostgreSQL, see module docstring.
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def pool():
    ensure_database(DATABASE_URL)
    pool = open_pool(DATABASE_URL)
    apply_schema(pool)
    with pool.connection() as conn:
        conn.execute("TRUNCATE incidents, deployments, strategy_stats")
    yield pool
    pool.close()


def test_incident_ids_are_sequential_and_readable(pool):
    store = IncidentStore(pool)
    first = store.create("svc-a", "critical", "t", {})
    second = store.create("svc-b", "critical", "t", {})

    assert int(second.split("-")[1]) == int(first.split("-")[1]) + 1


def test_state_round_trips_through_jsonb(pool):
    store = IncidentStore(pool)
    incident_id = store.create("svc-c", "critical", "t", {})
    store.save_state(incident_id, {"trace": [{"step": "intake"}], "confidence": 0.8}, "PENDING_APPROVAL")

    row = store.get(incident_id)
    assert (row["status"], row["state"]["confidence"]) == ("PENDING_APPROVAL", 0.8)


def test_claim_status_lets_only_one_decider_win(pool):
    store = IncidentStore(pool)
    incident_id = store.create("svc-d", "critical", "t", {})
    store.set_status(incident_id, "PENDING_APPROVAL")

    assert [store.claim_status(incident_id, "PENDING_APPROVAL", "DECISION_RECORDED") for _ in range(2)] == [True, False]


def test_find_open_ignores_terminal_incidents(pool):
    store = IncidentStore(pool)
    incident_id = store.create("svc-e", "critical", "t", {})
    store.set_status(incident_id, "RESOLVED")

    assert store.find_open("svc-e") is None


def test_cursor_pagination_walks_backwards(pool):
    store = IncidentStore(pool)
    ids = [store.create("svc-f", "critical", str(i), {}) for i in range(3)]

    page = store.list(2, before=ids[-1])

    assert [r["id"] for r in page] == [ids[1], ids[0]]


def test_recent_deployments_are_returned(pool):
    store = DeploymentStore(pool)
    store.add(DeploymentIn(service="auth-service", version="v2.4.0", changes=["TTL dropped"]))

    assert store.recent(10)[0]["changes"] == ["TTL dropped"]


def test_strategy_scores_accumulate(pool):
    scores = StrategyScores(pool)
    scores.record(recommended="RB-CACHE-002", final="RB-CACHE-001", decision="MODIFIED", outcome="RESOLVED")
    scores.record(recommended="RB-CACHE-001", final="RB-CACHE-001", decision="APPROVED", outcome="RESOLVED")

    by_id = {s["runbook_id"]: s["score"] for s in scores.all()}
    assert by_id == {"RB-CACHE-001": 1.0, "RB-CACHE-002": 0.0}


def test_langgraph_checkpointer_works_on_shared_pool(pool):
    saver = PostgresSaver(pool)
    saver.setup()

    assert saver.get_tuple({"configurable": {"thread_id": "never-used"}}) is None
