"""Node 2 — Evidence Collection: call the controlled tools, then compute findings deterministically."""
from app.agents.analysis import build_findings, compute_signals
from app.agents.deps import AgentDeps
from app.agents.state import IncidentState, trace
from app.tools.base import run_tool

EVIDENCE_WINDOW = "1m"


def _git_changes(deployments: list[dict]) -> list[dict]:
    return [{"service": d["service"], "version": d["version"], "commit": d.get("commit_sha"),
             "author": d.get("author"), "changes": d.get("changes", [])} for d in deployments]


def make_evidence(deps: AgentDeps):
    settings = deps.settings

    def evidence(state: IncidentState) -> dict:
        results = {
            "get_metrics": run_tool("get_metrics", lambda: deps.prometheus.snapshot(EVIDENCE_WINDOW)),
            "get_logs": run_tool("get_logs", lambda: deps.read_logs(settings.evidence_window_minutes)),
            "get_service_health": run_tool("get_service_health", deps.health_check),
            "get_recent_deployments": run_tool(
                "get_recent_deployments", lambda: deps.deployments.recent(settings.deploy_lookback_minutes)),
        }
        deployments = results["get_recent_deployments"].data or []
        results["get_git_changes"] = run_tool("get_git_changes", lambda: _git_changes(deployments))
        metrics = results["get_metrics"].data or {}
        logs = results["get_logs"].data or {}
        health = results["get_service_health"].data or {"status": "unreachable"}
        errors = [f"{name}: {r.error}" for name, r in results.items() if not r.is_ok]
        findings = build_findings(metrics, logs, health, deployments)
        return {
            "metrics": metrics, "logs": logs, "health": health, "recent_changes": deployments,
            "tool_errors": errors, "findings": findings,
            "signals": compute_signals(metrics, logs, health, deployments),
            "trace": trace("evidence", f"Evidence collected from {len(results) - len(errors)}/{len(results)} tools",
                           findings + [f"⚠ {e}" for e in errors], "warning" if errors else "ok"),
        }

    return evidence
