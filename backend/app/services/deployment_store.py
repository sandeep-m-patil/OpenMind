"""Deployment events, used to correlate "what changed right before the incident?"."""
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.schemas.deployments import DeploymentIn

_COLUMNS = "id, service, version, commit_sha, author, description, changes, source, deployed_at"


class DeploymentStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, deployment: DeploymentIn) -> dict:
        with self._pool.connection() as conn:
            return conn.execute(
                "INSERT INTO deployments (service, version, commit_sha, author, description, changes, source) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {_COLUMNS}",
                (
                    deployment.service,
                    deployment.version,
                    deployment.commit_sha,
                    deployment.author,
                    deployment.description,
                    Jsonb(deployment.changes),
                    deployment.source,
                ),
            ).fetchone()

    def recent(self, lookback_minutes: int, limit: int = 20) -> list[dict]:
        with self._pool.connection() as conn:
            return conn.execute(
                f"SELECT {_COLUMNS} FROM deployments WHERE deployed_at >= now() - make_interval(mins => %s) "
                "ORDER BY deployed_at DESC LIMIT %s",
                (lookback_minutes, limit),
            ).fetchall()
