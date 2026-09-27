"""Node 8 — Verification: poll real metrics until they recover or time out. Before vs after."""
from app.agents.deps import AgentDeps
from app.agents.state import IncidentState, trace
from app.agents.verdict import evaluate
from app.tools.base import run_tool

VERIFY_WINDOW = "30s"  # short window so pre-remediation samples age out quickly
MANUAL_TIMEOUT_MULTIPLIER = 2
MS_PER_SECOND = 1000
PERCENT = 100


def _fmt(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds * MS_PER_SECOND:.0f} ms"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * PERCENT:.0f}%"


def make_verification(deps: AgentDeps):
    settings = deps.settings

    def verification(state: IncidentState) -> dict:
        before = state.get("metrics_before") or state.get("metrics") or {}
        category = (state.get("diagnosis") or {}).get("category")
        is_manual = state.get("human_decision", {}).get("decision") == "EXECUTE_MANUALLY"
        timeout = settings.verify_timeout_seconds * (MANUAL_TIMEOUT_MULTIPLIER if is_manual else 1)
        polls = max(1, timeout // settings.verify_poll_seconds)
        verdict, after, samples = None, {}, []
        for _ in range(polls):
            deps.sleep(settings.verify_poll_seconds)
            after = run_tool("get_metrics", lambda: deps.prometheus.snapshot(VERIFY_WINDOW)).data or {}
            health = run_tool("get_service_health", deps.health_check).data or {"status": "unreachable"}
            verdict = evaluate(before, after, health, settings.verify_p95_target_seconds, category)
            samples.append({"p95_seconds": after.get("p95_seconds"), "resolved": verdict.is_resolved})
            if verdict.is_resolved:
                break
        has_data = any(s["p95_seconds"] is not None for s in samples)
        outcome = "RESOLVED" if verdict.is_resolved else ("REMEDIATION_FAILED" if has_data else "VERIFICATION_INCONCLUSIVE")
        comparison = [
            f"P95: {_fmt(before.get('p95_seconds'))} → {_fmt(after.get('p95_seconds'))}",
            f"Cache hit ratio: {_pct(before.get('cache_hit_ratio'))} → {_pct(after.get('cache_hit_ratio'))}",
            f"Redis memory: {_pct(before.get('redis_memory_utilization'))} → {_pct(after.get('redis_memory_utilization'))}",
            f"Checks: {verdict.checks}" if has_data else "No traffic data during verification window",
        ]
        return {
            "verification_result": {"outcome": outcome, "before": before, "after": after,
                                    "verdict": verdict.to_dict(), "samples": samples},
            "outcome": outcome, "status": outcome,
            "trace": trace("verification", f"Verification: {outcome.replace('_', ' ')} (from real metrics)",
                           comparison, "ok" if outcome == "RESOLVED" else "error"),
        }

    return verification
