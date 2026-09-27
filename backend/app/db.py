"""PostgreSQL connection pool + schema for OpsMind's own records (separate `opsmind` database)."""
import logging
import re

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("opsmind.db")

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10
POOL_TIMEOUT_SECONDS = 10
STARTUP_WAIT_SECONDS = 60
SAFE_DB_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
FIRST_INCIDENT_NUMBER = 1001

SCHEMA_SQL = f"""
CREATE SEQUENCE IF NOT EXISTS incident_number_seq START {FIRST_INCIDENT_NUMBER};

CREATE TABLE IF NOT EXISTS incidents (
    id          TEXT PRIMARY KEY,
    service     TEXT        NOT NULL,
    severity    TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    status      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    state       JSONB       NOT NULL DEFAULT '{{}}'::jsonb
);
CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_service_status_idx ON incidents (service, status);
CREATE INDEX IF NOT EXISTS incidents_created_idx ON incidents (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS deployments (
    id          SERIAL PRIMARY KEY,
    service     TEXT        NOT NULL,
    version     TEXT        NOT NULL,
    commit_sha  TEXT,
    author      TEXT,
    description TEXT,
    changes     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    source      TEXT        NOT NULL DEFAULT 'api',
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS deployments_time_idx ON deployments (deployed_at DESC);

CREATE TABLE IF NOT EXISTS strategy_stats (
    runbook_id TEXT PRIMARY KEY,
    proposed   INTEGER NOT NULL DEFAULT 0,
    approved   INTEGER NOT NULL DEFAULT 0,
    modified   INTEGER NOT NULL DEFAULT 0,
    rejected   INTEGER NOT NULL DEFAULT 0,
    adopted    INTEGER NOT NULL DEFAULT 0,
    succeeded  INTEGER NOT NULL DEFAULT 0,
    failed     INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_database(database_url: str) -> None:
    """Create the target database if missing (the Postgres container only creates `shop`)."""
    params = conninfo_to_dict(database_url)
    db_name = params.get("dbname", "")
    if not SAFE_DB_NAME.match(db_name):
        raise ValueError(f"unsafe database name: {db_name!r}")
    admin_url = make_conninfo(database_url, dbname="postgres")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if not exists:
            # Identifiers can't be bound as parameters; the name is validated above and quoted here.
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            logger.info("created database", extra={"event": "db_created", "database": db_name})


def open_pool(database_url: str) -> ConnectionPool:
    # autocommit + prepare_threshold=0 are required by LangGraph's PostgresSaver on a shared pool.
    pool = ConnectionPool(
        database_url,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        timeout=POOL_TIMEOUT_SECONDS,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=STARTUP_WAIT_SECONDS)
    return pool


def apply_schema(pool: ConnectionPool) -> None:
    # One statement per execute: the pool uses prepared statements, which can't hold several commands.
    statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
    with pool.connection() as conn:
        for statement in statements:
            conn.execute(statement)
