"""Slack Block Kit messages for incidents (pure functions — easy to test and preview)."""
PERCENT = 100
MAX_FINDINGS = 5
ACTION_IDS = {"opsmind_approve": "APPROVED", "opsmind_reject": "REJECTED", "opsmind_manual": "EXECUTE_MANUALLY"}
RISK_EMOJI = {"LOW": "🟢", "MEDIUM": "🟠", "HIGH": "🔴"}
OUTCOME_EMOJI = {"RESOLVED": "✅", "REMEDIATION_FAILED": "❌", "REJECTED": "🚫",
                 "VERIFICATION_INCONCLUSIVE": "❔", "ERROR": "💥"}


def _button(text: str, action_id: str, value: str, style: str | None = None) -> dict:
    button = {"type": "button", "text": {"type": "plain_text", "text": text}, "action_id": action_id, "value": value}
    return {**button, "style": style} if style else button


def pending_blocks(incident: dict, dashboard_url: str) -> list[dict]:
    state, incident_id = incident["state"], incident["id"]
    diagnosis = state.get("diagnosis") or {}
    guidance = state.get("memory_guidance") or {}
    runbook, risk = state.get("recommended_runbook") or "none", state.get("risk") or "n/a"
    history = ", ".join(guidance.get("matched_incidents", [])) or "none"
    fields = [
        f"*Service:*\n{state.get('service')}", f"*Severity:*\n{state.get('severity')}",
        f"*Likely cause:*\n{diagnosis.get('category', 'unknown')}",
        f"*Confidence:*\n{(state.get('confidence') or 0) * PERCENT:.0f}%",
        f"*Historical match:*\n{history}", f"*Recommended runbook:*\n`{runbook}` {state.get('recommended_params') or ''}",
        f"*Risk:*\n{RISK_EMOJI.get(risk, '')} {risk}",
    ]
    findings = "\n".join(f"• {f}" for f in state.get("findings", [])[:MAX_FINDINGS])
    link = f"{dashboard_url}/incidents/{incident_id}"
    buttons = [
        _button("Approve", "opsmind_approve", incident_id, "primary"),
        {"type": "button", "text": {"type": "plain_text", "text": "Edit"}, "url": link, "action_id": "opsmind_edit"},
        _button("Reject", "opsmind_reject", incident_id, "danger"),
        _button("Execute manually", "opsmind_manual", incident_id),
    ]
    return [
        {"type": "header", "text": {"type": "plain_text", "text": f"🚨 {incident_id}: {state.get('title')}"}},
        {"type": "section", "fields": [{"type": "mrkdwn", "text": f} for f in fields]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Evidence*\n{findings or '_none_'}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Why*\n{diagnosis.get('rationale') or diagnosis.get('root_cause', '')}"}},
        {"type": "actions", "elements": buttons},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"<{link}|Open in OpsMind dashboard>"}]},
    ]


def finished_text(incident: dict) -> str:
    state = incident["state"]
    outcome = incident["status"]
    verification = (state.get("verification_result") or {})
    before = (verification.get("before") or {}).get("p95_seconds")
    after = (verification.get("after") or {}).get("p95_seconds")
    change = f" P95 {before:.2f}s → {after:.2f}s." if before is not None and after is not None else ""
    lesson = state.get("learning_summary") or ""
    return f"{OUTCOME_EMOJI.get(outcome, 'ℹ️')} *{incident['id']}: {outcome.replace('_', ' ')}*.{change}\n🧠 {lesson}"
