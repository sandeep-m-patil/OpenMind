"""Deterministic diagnosis engine — used when no LLM key is configured or every LLM call fails.

It encodes a textbook first response (the "standard operating procedure") and then lets memory
override it: a runbook that operators overruled before is avoided, and one that verifiably resolved
a similar incident is preferred. This is what makes the second incident's recommendation differ
from the first, even with zero LLM calls.
"""
from app.agents.memory_guidance import overruled_ids, preferred_for
from app.schemas.diagnosis import DiagnosisOutput

# Standard first response per category, before any experience exists.
SOP_RUNBOOK = {
    "cache_saturation": "RB-CACHE-002",
    "bad_deployment": "RB-DEPLOY-001",
    "service_crash": "RB-SERVICE-001",
}
BASE_CONFIDENCE = {"cache_saturation": 0.8, "bad_deployment": 0.6, "service_crash": 0.7, "unknown": 0.3}
HISTORY_CONFIDENCE_BONUS = 0.12
MAX_CONFIDENCE = 0.97
ROOT_CAUSE = {
    "cache_saturation": "Redis cache saturation: memory is full, product cache entries are evicted or rejected, "
                        "so requests fall through to slow database queries.",
    "bad_deployment": "A recent deployment introduced the regression.",
    "service_crash": "The application service is unhealthy.",
    "unknown": "No single cause matches the evidence; manual investigation required.",
}


def categorize(signals: dict) -> str:
    if signals.get("is_redis_saturated") or (signals.get("is_hit_ratio_low") and signals.get("cache_write_rejections")):
        return "cache_saturation"
    if signals.get("is_service_unhealthy"):
        return "service_crash"
    if signals.get("is_error_rate_high") and signals.get("has_recent_deployment"):
        return "bad_deployment"
    return "unknown"


def choose_runbook(category: str, guidance: dict) -> tuple[str | None, list[str]]:
    notes: list[str] = []
    preferred = preferred_for(guidance, category)
    if preferred:
        notes.append(f"{preferred['incident_id']} was resolved with {preferred['runbook']} — reusing it.")
        return preferred["runbook"], notes
    runbook = SOP_RUNBOOK.get(category)
    if runbook and runbook in overruled_ids(guidance):
        notes.append(f"Operators previously overruled {runbook}; no validated alternative in memory.")
    return runbook, notes


def diagnose(signals: dict, findings: list[str], guidance: dict) -> DiagnosisOutput:
    category = categorize(signals)
    runbook, notes = choose_runbook(category, guidance)
    confidence = BASE_CONFIDENCE[category]
    if guidance.get("matched_incidents"):
        confidence = min(MAX_CONFIDENCE, confidence + HISTORY_CONFIDENCE_BONUS)
    rationale = " ".join(notes) or ("No similar past incident in memory; using the standard first response."
                                    if runbook else "No automated remediation applies.")
    return DiagnosisOutput(
        root_cause=ROOT_CAUSE[category],
        category=category,
        confidence=round(confidence, 2),
        evidence=findings[:6],
        recommended_runbook=runbook,
        runbook_params={},
        rationale=rationale,
        historical_references=guidance.get("matched_incidents", [])[:5],
    )
