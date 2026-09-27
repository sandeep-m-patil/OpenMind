"""In-memory fakes for every external dependency, so the whole LangGraph workflow runs in tests."""
import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import load_settings
from app.services.executor import ExecutionResult
from app.services.memory import MemoryUnavailable, RecalledMemory
from app.services.strategy_scores import COUNTERS, outcome_counters, proposal_counters, score

REPO = Path(__file__).resolve().parents[2]
INCIDENT_METRICS = {"p50_seconds": 3.0, "p95_seconds": 5.0, "p99_seconds": 6.0, "baseline_p95_seconds": 0.013,
                    "request_rate": 50.0, "error_rate": 0.0, "cache_hit_ratio": 0.05,
                    "redis_memory_utilization": 1.0, "redis_evictions_per_second": 30.0, "redis_up": 1.0}
HEALTHY_METRICS = {**INCIDENT_METRICS, "p50_seconds": 0.01, "p95_seconds": 0.03, "p99_seconds": 0.05,
                   "cache_hit_ratio": 0.97, "redis_memory_utilization": 0.06, "redis_evictions_per_second": 0.0}
INCIDENT_LOGS = {"window_minutes": 5, "total_lines": 900, "by_level": {"WARNING": 600},
                 "top_warnings": [{"message": "WARNING: cache write rejected", "count": 500}], "samples": []}


def make_settings(**overrides):
    base = dataclasses.replace(load_settings(), runbooks_dir=str(REPO / "runbooks"), ansible_dir=str(REPO / "infrastructure" / "ansible"),
                               verify_poll_seconds=1, verify_timeout_seconds=3, is_background_enabled=False)
    return dataclasses.replace(base, **overrides)


class FakePrometheus:
    def __init__(self) -> None:
        self.metrics = dict(INCIDENT_METRICS)
        self.is_up = True

    def snapshot(self, window: str = "1m") -> dict:
        if not self.is_up:
            raise ConnectionError("prometheus down")
        return dict(self.metrics)

    def is_reachable(self) -> bool:
        return self.is_up


class FakeMemory:
    """Behaves like Hindsight for our purposes: whatever was retained is recalled."""

    def __init__(self) -> None:
        self.items: list = []
        self.is_up = True

    def retain(self, items) -> dict:
        if not self.is_up:
            raise MemoryUnavailable("down")
        self.items.extend(items)
        return {"success": True}

    def recall(self, query: str, tags=None) -> list[RecalledMemory]:
        if not self.is_up:
            raise MemoryUnavailable("down")
        return [RecalledMemory(id=f"m{i}", text=item.content, score=1.0, document_id=item.document_id,
                               metadata=item.metadata, tags=item.tags, type="world") for i, item in enumerate(self.items)]

    def is_available(self) -> bool:
        return self.is_up


class FakeExecutor:
    def __init__(self, prometheus: FakePrometheus) -> None:
        self.calls: list[tuple[str, dict, bool]] = []
        self.prometheus = prometheus
        self.should_fail_check = False
        self.fixes_incident = True

    def run(self, runbook, params, is_check: bool) -> ExecutionResult:
        self.calls.append((runbook.id, params, is_check))
        ok = not (is_check and self.should_fail_check)
        if ok and not is_check and self.fixes_incident:
            self.prometheus.metrics = dict(HEALTHY_METRICS)
        return ExecutionResult(runbook.id, "check" if is_check else "apply", ok, 0 if ok else 2, False, 0.1,
                               ["ansible-playbook", runbook.playbook], "ok", {"dry_run": is_check})


class FakeStrategies:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def _bump(self, runbook_id: str, counters: list[str]) -> None:
        row = self.rows.setdefault(runbook_id, {"runbook_id": runbook_id, **{c: 0 for c in COUNTERS}})
        for counter in counters:
            row[counter] += 1

    def record(self, *, recommended, final, decision, outcome) -> None:
        if recommended:
            self._bump(recommended, proposal_counters(decision))
        if final:
            self._bump(final, outcome_counters(decision, recommended, final, outcome))

    def all(self) -> list[dict]:
        return [{**row, "score": score(row)} for row in self.rows.values()]


class FakeDeployments:
    def __init__(self) -> None:
        self.rows = [{"id": 1, "service": "auth-service", "version": "v2.4.0", "commit_sha": "9f3c2e1",
                      "author": "dev", "description": "Refactor session storage", "changes": ["TTL dropped"],
                      "source": "test", "deployed_at": datetime.now(timezone.utc) - timedelta(minutes=7)}]

    def recent(self, lookback_minutes: int, limit: int = 20) -> list[dict]:
        return list(self.rows)

    def add(self, deployment) -> dict:
        row = {**deployment.model_dump(), "id": len(self.rows) + 1, "deployed_at": datetime.now(timezone.utc)}
        self.rows.append(row)
        return row


class FakeIncidentStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self._next = 1001

    def create(self, service, severity, title, state) -> str:
        incident_id = f"INC-{self._next}"
        self._next += 1
        now = datetime.now(timezone.utc) + timedelta(microseconds=self._next)
        self.rows[incident_id] = {"id": incident_id, "service": service, "severity": severity, "title": title,
                                  "status": "INVESTIGATING", "created_at": now, "updated_at": now,
                                  "state": {**state, "incident_id": incident_id}}
        return incident_id

    def get(self, incident_id):
        return self.rows.get(incident_id)

    def list(self, limit, before=None):
        rows = sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)
        if before:
            rows = [r for r in rows if r["created_at"] < self.rows[before]["created_at"]]
        return rows[:limit]

    def find_open(self, service):
        from app.services.incident_store import TERMINAL_STATUSES

        return next((r for r in self.rows.values() if r["service"] == service and r["status"] not in TERMINAL_STATUSES), None)

    def save_state(self, incident_id, state, status=None):
        self.rows[incident_id]["state"] = state
        if status:
            self.rows[incident_id]["status"] = status

    def claim_status(self, incident_id, expected, new) -> bool:
        if self.rows[incident_id]["status"] != expected:
            return False
        self.rows[incident_id]["status"] = new
        return True


class RecordingNotifier:
    is_enabled = False

    def __init__(self) -> None:
        self.pending: list[str] = []
        self.finished: list[str] = []

    def incident_pending(self, incident) -> None:
        self.pending.append(incident["id"])

    def incident_finished(self, incident) -> None:
        self.finished.append(incident["id"])
