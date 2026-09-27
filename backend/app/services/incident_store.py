"""Incident records. The full workflow state is kept as JSONB so the dashboard can show every step."""
import json
from functools import partial

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

TERMINAL_STATUSES = frozenset(
    {"RESOLVED", "REMEDIATION_FAILED", "VERIFICATION_INCONCLUSIVE", "REJECTED", "ERROR"}
)
_dumps = partial(json.dumps, default=str)
_COLUMNS = "id, service, severity, title, status, created_at, updated_at, state"


def _jsonb(value: dict) -> Jsonb:
    return Jsonb(value, dumps=_dumps)


class IncidentStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(self, service: str, severity: str, title: str, state: dict) -> str:
        with self._pool.connection() as conn:
            number = conn.execute("SELECT nextval('incident_number_seq') AS n").fetchone()["n"]
            incident_id = f"INC-{number}"
            conn.execute(
                "INSERT INTO incidents (id, service, severity, title, status, state) VALUES (%s, %s, %s, %s, %s, %s)",
                (incident_id, service, severity, title, "INVESTIGATING", _jsonb({**state, "incident_id": incident_id})),
            )
        return incident_id

    def get(self, incident_id: str) -> dict | None:
        with self._pool.connection() as conn:
            return conn.execute(f"SELECT {_COLUMNS} FROM incidents WHERE id = %s", (incident_id,)).fetchone()

    def list(self, limit: int, before: str | None = None) -> list[dict]:
        """Newest first, cursor-paginated: pass the last id you saw as `before`."""
        with self._pool.connection() as conn:
            if before is None:
                return conn.execute(
                    f"SELECT {_COLUMNS} FROM incidents ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)
                ).fetchall()
            return conn.execute(
                f"SELECT {_COLUMNS} FROM incidents WHERE (created_at, id) < "
                "(SELECT created_at, id FROM incidents WHERE id = %s) ORDER BY created_at DESC, id DESC LIMIT %s",
                (before, limit),
            ).fetchall()

    def find_open(self, service: str) -> dict | None:
        with self._pool.connection() as conn:
            return conn.execute(
                f"SELECT {_COLUMNS} FROM incidents WHERE service = %s AND NOT (status = ANY(%s)) "
                "ORDER BY created_at DESC LIMIT 1",
                (service, list(TERMINAL_STATUSES)),
            ).fetchone()

    def save_state(self, incident_id: str, state: dict, status: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE incidents SET state = %s, status = COALESCE(%s, status), updated_at = now() WHERE id = %s",
                (_jsonb(state), status, incident_id),
            )

    def claim_status(self, incident_id: str, expected: str, new: str) -> bool:
        """Atomic compare-and-set, so two approvers (Slack + dashboard) can't both win."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "UPDATE incidents SET status = %s, updated_at = now() WHERE id = %s AND status = %s RETURNING id",
                (new, incident_id, expected),
            ).fetchone()
        return row is not None

    def set_status(self, incident_id: str, status: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("UPDATE incidents SET status = %s, updated_at = now() WHERE id = %s", (status, incident_id))
