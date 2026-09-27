"""Deterministic risk / policy gate. Runs on the AI's proposal AND on the human's final action.

Rules (no LLM involved):
  * the runbook must exist in the catalog and its parameters must validate;
  * every action requires human approval — nothing is ever auto-executed;
  * if operators previously overruled this runbook for this service, risk is raised one level
    and the reason is shown to the approver.
"""
from dataclasses import dataclass, field

from app.services.runbooks import RISK_LEVELS, InvalidRunbook, RunbookCatalog, validate_params


@dataclass
class PolicyResult:
    is_allowed: bool
    risk: str | None
    params: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = True

    def to_dict(self) -> dict:
        return {
            "is_allowed": self.is_allowed,
            "risk": self.risk,
            "params": self.params,
            "reasons": self.reasons,
            "requires_approval": self.requires_approval,
        }


def _raise_one_level(risk: str) -> str:
    index = RISK_LEVELS.index(risk)
    return RISK_LEVELS[min(index + 1, len(RISK_LEVELS) - 1)]


class PolicyGate:
    def __init__(self, catalog: RunbookCatalog) -> None:
        self._catalog = catalog

    def evaluate(self, runbook_id: str | None, params: dict | None, overruled_runbooks: set[str]) -> PolicyResult:
        if runbook_id is None:
            return PolicyResult(is_allowed=False, risk=None, reasons=["no automated runbook proposed — manual investigation"])
        try:
            runbook = self._catalog.get(runbook_id)
            clean = validate_params(runbook, params)
        except InvalidRunbook as exc:
            return PolicyResult(is_allowed=False, risk=None, reasons=[str(exc)])
        risk, reasons = runbook.risk, [f"base risk of {runbook.id} is {runbook.risk}"]
        if runbook_id in overruled_runbooks:
            risk = _raise_one_level(risk)
            reasons.append(f"operators previously overruled {runbook_id} for this service → risk raised to {risk}")
        if risk == "HIGH":
            reasons.append("HIGH risk: explicit human approval required; review side effects carefully")
        return PolicyResult(is_allowed=True, risk=risk, params=clean, reasons=reasons)
