"""End-to-end behaviour of the LangGraph workflow with fakes — including the learning loop."""
import pytest

from app.schemas.decisions import DecisionIn
from app.services.decisions import DecisionError
from app.services.workflow import Conflict, NotFound
from tests.fakes import INCIDENT_METRICS

CORRECTION = "Do not clear the entire cache. Only remove stale session keys."


def _open(env) -> str:
    incident_id, _ = env.runner.open_incident(service="product-api", severity="critical", title="High latency")
    return incident_id


def _state(env, incident_id) -> dict:
    return env.incidents.get(incident_id)["state"]


def _modify_to_targeted(env, incident_id) -> None:
    env.runner.decide(incident_id, DecisionIn(decision="MODIFIED", operator="sre", runbook_id="RB-CACHE-001",
                                              params={"max_idle_hours": 24}, comment=CORRECTION))


def _new_incident_after_recovery(env) -> str:
    env.prometheus.metrics = dict(INCIDENT_METRICS)
    return _open(env)


def test_workflow_stops_for_human_approval(env):
    incident_id = _open(env)

    assert (env.incidents.get(incident_id)["status"], env.executor.calls) == ("PENDING_APPROVAL", [])


def test_first_incident_without_memory_proposes_standard_flush(env):
    state = _state(env, _open(env))

    assert (state["recommended_runbook"], state["risk"]) == ("RB-CACHE-002", "HIGH")


def test_pending_incident_is_announced(env):
    incident_id = _open(env)

    assert env.notifier.pending == [incident_id]


def test_trace_covers_every_investigation_step(env):
    steps = [t["step"] for t in _state(env, _open(env))["trace"]]

    assert steps == ["intake", "evidence", "recall", "diagnosis", "planner", "approval"]


def test_modified_decision_runs_dry_run_then_apply_of_the_human_choice(env):
    incident_id = _open(env)
    _modify_to_targeted(env, incident_id)

    assert env.executor.calls == [("RB-CACHE-001", {"max_idle_hours": 24}, True), ("RB-CACHE-001", {"max_idle_hours": 24}, False)]


def test_recovery_is_verified_from_metrics(env):
    incident_id = _open(env)
    _modify_to_targeted(env, incident_id)

    assert env.incidents.get(incident_id)["status"] == "RESOLVED"


def test_experience_is_retained_with_the_operator_correction(env):
    incident_id = _open(env)
    _modify_to_targeted(env, incident_id)

    metadata = env.memory.items[0].metadata
    assert (metadata["recommended_runbook"], metadata["final_runbook"], metadata["operator_comment"]) == (
        "RB-CACHE-002", "RB-CACHE-001", CORRECTION)


def test_second_incident_recommends_what_the_human_taught(env):
    _modify_to_targeted(env, _open(env))

    state = _state(env, _new_incident_after_recovery(env))

    assert (state["recommended_runbook"], state["risk"]) == ("RB-CACHE-001", "LOW")


def test_second_incident_is_more_confident_and_cites_history(env):
    first = _open(env)
    first_confidence = _state(env, first)["confidence"]
    _modify_to_targeted(env, first)

    state = _state(env, _new_incident_after_recovery(env))

    assert (state["confidence"] > first_confidence, state["memory_guidance"]["matched_incidents"]) == (True, [first])


def test_rejection_skips_execution_and_is_learned(env):
    incident_id = _open(env)
    env.runner.decide(incident_id, DecisionIn(decision="REJECTED", operator="sre", comment="not now"))

    assert (env.executor.calls, env.incidents.get(incident_id)["status"], env.memory.items[0].metadata["decision"]) == (
        [], "REJECTED", "REJECTED")


def test_manual_execution_is_still_verified(env):
    incident_id = _open(env)
    env.prometheus.metrics["p95_seconds"] = 0.02  # the human fixed it themselves
    env.prometheus.metrics["cache_hit_ratio"] = 0.99

    env.runner.decide(incident_id, DecisionIn(decision="EXECUTE_MANUALLY", operator="sre"))

    assert (env.executor.calls, env.incidents.get(incident_id)["status"]) == ([], "RESOLVED")


def test_failed_dry_run_aborts_before_apply(env):
    incident_id = _open(env)
    env.executor.should_fail_check = True

    env.runner.decide(incident_id, DecisionIn(decision="APPROVED", operator="sre"))

    assert (len(env.executor.calls), env.incidents.get(incident_id)["status"]) == (1, "REMEDIATION_FAILED")


def test_remediation_that_does_not_help_is_marked_failed(env):
    incident_id = _open(env)
    env.executor.fixes_incident = False

    env.runner.decide(incident_id, DecisionIn(decision="APPROVED", operator="sre"))

    assert env.incidents.get(incident_id)["status"] == "REMEDIATION_FAILED"


def test_no_traffic_during_verification_is_inconclusive(env):
    incident_id = _open(env)
    env.executor.fixes_incident = False
    env.prometheus.metrics["p95_seconds"] = None

    env.runner.decide(incident_id, DecisionIn(decision="APPROVED", operator="sre"))

    assert env.incidents.get(incident_id)["status"] == "VERIFICATION_INCONCLUSIVE"


def test_hindsight_outage_does_not_stop_the_workflow(env):
    env.memory.is_up = False
    incident_id = _open(env)
    _modify_to_targeted(env, incident_id)

    assert (env.incidents.get(incident_id)["status"], _state(env, incident_id)["memory_retained"]) == ("RESOLVED", False)


def test_monitoring_outage_is_reported_as_missing_evidence(env):
    env.prometheus.is_up = False

    state = _state(env, _open(env))

    assert state["tool_errors"][0].startswith("get_metrics")


def test_open_incident_absorbs_duplicate_alerts(env):
    first = _open(env)

    assert env.runner.open_incident(service="product-api", severity="critical", title="again") == (first, False)


def test_decision_on_unknown_incident_is_not_found(env):
    with pytest.raises(NotFound):
        env.runner.decide("INC-9", DecisionIn(decision="APPROVED", operator="sre"))


def test_second_decision_conflicts(env):
    incident_id = _open(env)
    env.runner.decide(incident_id, DecisionIn(decision="REJECTED", operator="a"))

    with pytest.raises(Conflict):
        env.runner.decide(incident_id, DecisionIn(decision="APPROVED", operator="b"))


def test_out_of_policy_modification_is_refused(env):
    incident_id = _open(env)

    with pytest.raises(DecisionError):
        env.runner.decide(incident_id, DecisionIn(decision="MODIFIED", operator="sre", runbook_id="RB-CACHE-001",
                                                  params={"max_idle_hours": 99999}))


def test_workflow_crash_marks_incident_error(env, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(env.deployments, "recent", explode)
    monkeypatch.setattr("app.agents.nodes.evidence.build_findings", explode)

    incident_id = _open(env)

    assert env.incidents.get(incident_id)["status"] == "ERROR"
