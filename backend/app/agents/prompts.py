"""Prompt for the single diagnosis+planning LLM call. Evidence is pre-digested by deterministic code."""
import json

SYSTEM_PROMPT = """You are OpsMind, an SRE copilot. You diagnose production incidents from evidence
and recommend ONE remediation runbook from a fixed catalog. A human approves every action.

Rules:
- Use only the evidence given. Never invent metrics, logs or incidents.
- recommended_runbook MUST be an id from the catalog, or null if no runbook is appropriate.
- runbook_params may only contain parameters the chosen runbook declares.
- Past incidents from memory are the organization's experience. If operators overruled a runbook
  for a similar incident, do not recommend it again unless the evidence is clearly different,
  and say why. If a runbook verifiably resolved a similar incident, prefer it and cite the incident.
- evidence: short factual bullet strings (max 6). confidence: 0..1.
- Return ONLY a JSON object with keys: root_cause, category, confidence, evidence,
  recommended_runbook, runbook_params, rationale, historical_references.
- category is one of: cache_saturation, bad_deployment, service_crash, database_slowdown, unknown.
"""


def _memories_block(memories: list[dict]) -> str:
    if not memories:
        return "(no similar past incidents found in memory)"
    return "\n".join(f"- [{m.get('document_id')}] (relevance {m.get('score', 0):.2f}) {m['text']}" for m in memories)


def build_user_prompt(state: dict, catalog: list[dict], strategy_scores: list[dict]) -> str:
    metrics = {k: v for k, v in (state.get("metrics") or {}).items() if v is not None}
    logs = state.get("logs") or {}
    sections = {
        "INCIDENT": f"{state.get('service')} — {state.get('title')} (severity {state.get('severity')})",
        "FINDINGS (computed deterministically)": "\n".join(f"- {f}" for f in state.get("findings", [])),
        "RAW METRICS": json.dumps(metrics, default=str),
        "LOG SUMMARY": json.dumps({"by_level": logs.get("by_level"), "top_warnings": logs.get("top_warnings")}, default=str),
        "RECENT CHANGES": json.dumps(state.get("recent_changes", []), default=str)[:2000],
        "PAST INCIDENTS FROM MEMORY (Hindsight)": _memories_block(state.get("historical_memories", [])),
        "OPERATOR FEEDBACK FROM MEMORY": "\n".join(state.get("memory_guidance", {}).get("operator_comments", [])) or "(none)",
        "STRATEGY SCORES (succeeded / attempts)": json.dumps(strategy_scores, default=str),
        "RUNBOOK CATALOG": json.dumps(catalog, default=str),
    }
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections.items())
