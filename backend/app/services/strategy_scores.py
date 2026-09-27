"""Phase 14 — lightweight strategy scoring (not reinforcement learning).

Per runbook we count how humans reacted when it was proposed and how it did when executed:

    score = succeeded / (proposed + adopted)

`adopted` = times a human switched *to* this runbook (a MODIFIED decision). So a strategy that is
often proposed but overruled scores low, and one that humans pick and that verifiably works scores high.
Example from the spec: approved 9, modified 1, succeeded 9 → 9 / 10 = 0.90.
"""
from psycopg_pool import ConnectionPool

COUNTERS = ("proposed", "approved", "modified", "rejected", "adopted", "succeeded", "failed")
_DECISION_COUNTER = {"APPROVED": "approved", "MODIFIED": "modified", "REJECTED": "rejected"}
EXECUTED_DECISIONS = {"APPROVED", "MODIFIED"}
SCORED_OUTCOMES = {"RESOLVED": "succeeded", "REMEDIATION_FAILED": "failed"}


def score(stats: dict) -> float | None:
    attempts = stats.get("proposed", 0) + stats.get("adopted", 0)
    return round(stats.get("succeeded", 0) / attempts, 2) if attempts else None


def proposal_counters(decision: str) -> list[str]:
    """Counters for the runbook the AI proposed."""
    return ["proposed"] + ([_DECISION_COUNTER[decision]] if decision in _DECISION_COUNTER else [])


def outcome_counters(decision: str, recommended: str | None, final: str, outcome: str | None) -> list[str]:
    """Counters for the runbook that actually ran (only automated executions with a verified outcome)."""
    if decision not in EXECUTED_DECISIONS or outcome not in SCORED_OUTCOMES:
        return []
    counters = [SCORED_OUTCOMES[outcome]]
    if final != recommended:
        counters.append("adopted")
    return counters


class StrategyScores:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def _increment(self, runbook_id: str, counters: list[str]) -> None:
        if not counters:
            return
        if any(c not in COUNTERS for c in counters):  # column names come only from the allowlist
            raise ValueError(f"unknown counter in {counters}")
        assignments = ", ".join(f"{c} = strategy_stats.{c} + 1" for c in counters)
        columns = ", ".join(counters)
        values = ", ".join("1" for _ in counters)
        with self._pool.connection() as conn:
            conn.execute(
                f"INSERT INTO strategy_stats (runbook_id, {columns}) VALUES (%s, {values}) "
                f"ON CONFLICT (runbook_id) DO UPDATE SET {assignments}",
                (runbook_id,),
            )

    def record(self, *, recommended: str | None, final: str | None, decision: str, outcome: str | None) -> None:
        if recommended:
            self._increment(recommended, proposal_counters(decision))
        if final:
            self._increment(final, outcome_counters(decision, recommended, final, outcome))

    def all(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_stats ORDER BY runbook_id").fetchall()
        return [{**row, "score": score(row)} for row in rows]
