"""Turn recalled Hindsight memories into structured guidance for the planner.

Each incident memory we retain carries metadata (see agents/nodes/learning.py):
    incident_id, category, recommended_runbook, final_runbook, decision, outcome, operator_comment
From those we derive:
    preferred  — runbooks that verifiably resolved a similar incident
    overruled  — runbooks operators rejected or replaced (with their reasons)
"""


def derive_guidance(memories: list[dict]) -> dict:
    preferred: dict[str, dict] = {}
    overruled: dict[str, dict] = {}
    comments: list[str] = []
    for memory in memories:
        meta = memory.get("metadata") or {}
        incident = meta.get("incident_id", memory.get("document_id") or "?")
        recommended, final = meta.get("recommended_runbook"), meta.get("final_runbook")
        decision, outcome = meta.get("decision"), meta.get("outcome")
        if final and outcome == "RESOLVED" and final not in preferred:
            preferred[final] = {"runbook": final, "incident_id": incident, "category": meta.get("category"),
                                "p95_before": meta.get("p95_before"), "p95_after": meta.get("p95_after")}
        is_replaced = decision == "MODIFIED" and recommended and final and recommended != final
        if recommended and (decision == "REJECTED" or is_replaced) and recommended not in overruled:
            overruled[recommended] = {"runbook": recommended, "incident_id": incident,
                                      "replaced_by": final if is_replaced else None,
                                      "reason": meta.get("operator_comment", "")}
        if meta.get("operator_comment"):
            comments.append(f"{incident}: {meta['operator_comment']}")
    return {
        "preferred": list(preferred.values()),
        "overruled": list(overruled.values()),
        "operator_comments": list(dict.fromkeys(comments)),
        "matched_incidents": sorted({(m.get("metadata") or {}).get("incident_id") for m in memories} - {None}),
    }


def overruled_ids(guidance: dict) -> set[str]:
    return {o["runbook"] for o in guidance.get("overruled", [])}


def preferred_for(guidance: dict, category: str) -> dict | None:
    for item in guidance.get("preferred", []):
        if item.get("category") in (category, None):
            return item
    return None
