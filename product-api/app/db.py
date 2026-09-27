"""PostgreSQL access for products. All queries are parameterized."""
import logging

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

logger = logging.getLogger("product_api.db")

MS_PER_SECOND = 1000
CATEGORIES = ("books", "electronics", "garden", "kitchen", "toys")
# Deterministic seed data: same products every time, so incidents are reproducible.
SEED_PRICE_BASE_CENTS = 499
SEED_PRICE_STEP_CENTS = 37
SEED_PRICE_RANGE_CENTS = 10_000
SEED_STOCK_STEP = 13
SEED_STOCK_RANGE = 500

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    price_cents INTEGER NOT NULL,
    stock       INTEGER NOT NULL
)
"""
INSERT_SQL = "INSERT INTO products (name, category, price_cents, stock) VALUES (%s, %s, %s, %s)"
GET_SQL = "SELECT id, name, category, price_cents, stock FROM products WHERE id = %s"
LIST_SQL = "SELECT id, name, category, price_cents, stock FROM products ORDER BY id LIMIT %s"


def _seed_row(index: int) -> tuple:
    return (
        f"Product {index:03d}",
        CATEGORIES[index % len(CATEGORIES)],
        SEED_PRICE_BASE_CENTS + (index * SEED_PRICE_STEP_CENTS) % SEED_PRICE_RANGE_CENTS,
        (index * SEED_STOCK_STEP) % SEED_STOCK_RANGE,
    )


class ProductRepository:
    def __init__(self, pool: ConnectionPool, slow_query_ms: int) -> None:
        self._pool = pool
        self._slow_query_seconds = slow_query_ms / MS_PER_SECOND

    def ensure_seeded(self, count: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)
            existing = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
            if existing >= count:
                return
            rows = [_seed_row(i) for i in range(existing + 1, count + 1)]
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
        logger.info("seeded products", extra={"event": "db_seed", "inserted": len(rows)})

    def get_product(self, product_id: int) -> dict | None:
        with self._pool.connection() as conn:
            self._simulate_query_cost(conn)
            return conn.execute(GET_SQL, (product_id,)).fetchone()

    def list_products(self, limit: int) -> list[dict]:
        with self._pool.connection() as conn:
            self._simulate_query_cost(conn)
            return conn.execute(LIST_SQL, (limit,)).fetchall()

    def ping(self) -> bool:
        try:
            with self._pool.connection() as conn:
                conn.execute("SELECT 1")
            return True
        except (psycopg.Error, PoolTimeout):
            return False

    def _simulate_query_cost(self, conn: psycopg.Connection) -> None:
        if self._slow_query_seconds > 0:
            conn.execute("SELECT pg_sleep(%s)", (self._slow_query_seconds,))
