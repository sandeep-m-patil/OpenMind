"""Build the learning record retained in Hindsight after every incident (deterministic, no LLM).

The narrative text is what Hindsight embeds and recalls; the metadata is what memory_guidance.py
reads back to change future recommendations.
"""
MS_PER_SECOND = 1000
COMMENT_LIMIT = 300


def _ms(seconds) -> str:
    return "n/a" if seconds is None else (f"{seconds:.1f} s" if seconds >= 1 else f"{seconds * MS_PER_SECOND:.0f} ms")


def build_lesson(ctx: dict) -> str:
    service, category, outcome = ctx["service"], ctx["category"], ctx["outcome"]
    recommended, final, comment = ctx["recommended"], ctx["final"], ctx["comment"]
    change = f"P95 {_ms(ctx['p95_before'])} → {_ms(ctx['p95_after'])}"
    said = f" Operator said: \"{comment}\"." if comment else ""
    if ctx["decision"] == "REJECTED":
        return f"For {service} {category}, the operator rejected {recommended}.{said} Do not propose it again without new evidence."
    if outcome == "RESOLVED" and ctx["decision"] == "MODIFIED" and final != recommended:
        return (f"For {service} {category}, prefer {final} over {recommended}: the operator replaced the AI's "
                f"recommendation and {final} verifiably resolved the incident ({change}).{said}")
    if outcome == "RESOLVED":
        return f"{final} resolved {category} on {service} ({change}). Recommend it again for similar incidents.{said}"
    if outcome == "REMEDIATION_FAILED":
        return f"{final or recommended} did NOT resolve {category} on {service} ({change}). Try a different strategy.{said}"
    return f"Outcome for {service} {category} could not be verified (no traffic). Treat {final or recommended} as unproven.{said}"


def _context(state: dict) -> dict:
    decision = state.get("human_decision") or {}
    verification = state.get("verification_result") or {}
    verdict = verification.get("verdict") or {}
    before = state.get("metrics_before") or state.get("metrics") or {}
    return {
        "incident_id": state["incident_id"], "service": state["service"],
        "category": (state.get("diagnosis") or {}).get("category", "unknown"),
        "outcome": state.get("outcome") or ("REJECTED" if decision.get("decision") == "REJECTED" else "REMEDIATION_FAILED"),
        "decision": decision.get("decision", "NONE"), "operator": decision.get("operator", "unknown"),
        "comment": (decision.get("comment") or "")[:COMMENT_LIMIT],
        "recommended": state.get("recommended_runbook"),
        "final": (state.get("final_action") or {}).get("runbook_id"),
        "final_params": (state.get("final_action") or {}).get("params"),
        "p95_before": verdict.get("p95_before", before.get("p95_seconds")),
        "p95_after": verdict.get("p95_after"),
    }


def build_record(state: dict) -> dict:
    ctx = _context(state)
    diagnosis = state.get("diagnosis") or {}
    lesson = build_lesson(ctx)
    narrative = (
        f"Incident {ctx['incident_id']} on {ctx['service']} ({state.get('severity')}): {state.get('title')}. "
        f"Symptoms and evidence: {' '.join(state.get('findings', [])[:6])} "
        f"Diagnosis: {diagnosis.get('root_cause')} (category {ctx['category']}, confidence {diagnosis.get('confidence')}). "
        f"AI recommended {ctx['recommended'] or 'no automated runbook'}. "
        f"Human decision by {ctx['operator']}: {ctx['decision']}"
        + (f", final action {ctx['final']} {ctx['final_params']}" if ctx["final"] else "")
        + (f", comment: \"{ctx['comment']}\"" if ctx["comment"] else "") + ". "
        f"Outcome: {ctx['outcome']} (P95 {_ms(ctx['p95_before'])} → {_ms(ctx['p95_after'])}). Lesson: {lesson}"
    )
    metadata = {k: ("" if ctx[k] is None else str(ctx[k])) for k in
                ("incident_id", "service", "category", "outcome", "decision", "operator")}
    metadata.update(recommended_runbook=ctx["recommended"] or "", final_runbook=ctx["final"] or "",
                    operator_comment=ctx["comment"], p95_before=_ms(ctx["p95_before"]), p95_after=_ms(ctx["p95_after"]))
    tags = [f"service:{ctx['service']}", f"category:{ctx['category']}", f"outcome:{ctx['outcome'].lower()}"]
    return {"narrative": narrative, "lesson": lesson, "metadata": metadata, "tags": tags, "context": ctx}
