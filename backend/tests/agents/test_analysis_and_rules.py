from datetime import datetime, timedelta, timezone

from app.agents import rules
from app.agents.analysis import build_findings, compute_signals, memory_query
from app.agents.learning_record import build_lesson
from app.agents.memory_guidance import derive_guidance, preferred_for
from app.agents.verdict import evaluate
from tests.fakes import HEALTHY_METRICS, INCIDENT_LOGS, INCIDENT_METRICS

HEALTHY = {"status": "ok"}
RECENT = [{"service": "auth-service", "version": "v2", "description": "d",
           "deployed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}]
MODIFIED_MEMORY = {"document_id": "INC-1", "metadata": {
    "incident_id": "INC-1", "category": "cache_saturation", "recommended_runbook": "RB-CACHE-002",
    "final_runbook": "RB-CACHE-001", "decision": "MODIFIED", "outcome": "RESOLVED", "operator_comment": "no flush"}}


def _signals(**metrics):
    return compute_signals({**INCIDENT_METRICS, **metrics}, INCIDENT_LOGS, HEALTHY, RECENT)


def test_saturated_cache_is_detected():
    assert (_signals()["is_redis_saturated"], _signals()["cache_write_rejections"]) == (True, 500)


def test_findings_quantify_the_latency_regression():
    assert build_findings(INCIDENT_METRICS, INCIDENT_LOGS, HEALTHY, RECENT)[0] == \
        "P95 latency is 5.0 s vs a baseline of 13 ms (385× higher)."


def test_findings_mention_the_recent_deploy():
    assert any("auth-service v2 was deployed 5 min ago" in f for f in build_findings(INCIDENT_METRICS, {}, HEALTHY, RECENT))


def test_memory_query_describes_observed_symptoms():
    assert "Redis memory saturated" in memory_query("product-api", "High latency", _signals())


def test_unhealthy_service_is_categorized_as_crash():
    signals = compute_signals(HEALTHY_METRICS, {}, {"status": "degraded"}, [])

    assert rules.categorize(signals) == "service_crash"


def test_errors_after_deploy_suggest_bad_deployment():
    signals = compute_signals({**HEALTHY_METRICS, "error_rate": 0.2}, {}, HEALTHY, RECENT)

    assert rules.diagnose(signals, [], {}).recommended_runbook == "RB-DEPLOY-001"


def test_unknown_problems_get_no_automated_runbook():
    signals = compute_signals(HEALTHY_METRICS, {}, HEALTHY, [])

    assert rules.diagnose(signals, [], {}).recommended_runbook is None


def test_memory_overrides_the_standard_procedure():
    guidance = derive_guidance([MODIFIED_MEMORY])

    assert rules.diagnose(_signals(), [], guidance).recommended_runbook == "RB-CACHE-001"


def test_overruled_runbook_is_noted_when_no_alternative_exists():
    guidance = derive_guidance([{"metadata": {**MODIFIED_MEMORY["metadata"], "decision": "REJECTED",
                                              "final_runbook": "", "outcome": "REJECTED"}}])

    _, notes = rules.choose_runbook("cache_saturation", guidance)

    assert "previously overruled RB-CACHE-002" in notes[0]


def test_guidance_extracts_preference_and_overrule():
    guidance = derive_guidance([MODIFIED_MEMORY])

    assert (guidance["preferred"][0]["runbook"], guidance["overruled"][0]["replaced_by"]) == ("RB-CACHE-001", "RB-CACHE-001")


def test_preference_is_matched_by_category():
    assert preferred_for(derive_guidance([MODIFIED_MEMORY]), "bad_deployment") is None


def test_verdict_requires_real_improvement():
    verdict = evaluate(INCIDENT_METRICS, HEALTHY_METRICS, HEALTHY, 0.5, "cache_saturation")

    assert verdict.is_resolved and verdict.checks["cache_hit_ratio_recovered"]


def test_verdict_fails_while_latency_is_still_high():
    assert not evaluate(INCIDENT_METRICS, INCIDENT_METRICS, HEALTHY, 0.5, "cache_saturation").is_resolved


def test_verdict_without_data_is_not_resolved():
    assert evaluate(INCIDENT_METRICS, {}, HEALTHY, 0.5, None).has_data is False


def _lesson(**overrides):
    ctx = {"service": "product-api", "category": "cache_saturation", "outcome": "RESOLVED", "decision": "APPROVED",
           "recommended": "RB-CACHE-001", "final": "RB-CACHE-001", "comment": "", "p95_before": 5.0, "p95_after": 0.03}
    return build_lesson({**ctx, **overrides})


def test_lesson_for_failed_remediation_says_try_something_else():
    assert "did NOT resolve" in _lesson(outcome="REMEDIATION_FAILED")


def test_lesson_for_rejection_warns_against_reproposing():
    assert "Do not propose it again" in _lesson(decision="REJECTED", outcome="REJECTED")


def test_lesson_for_unverified_outcome_is_cautious():
    assert "unproven" in _lesson(outcome="VERIFICATION_INCONCLUSIVE")
