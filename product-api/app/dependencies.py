"""Wires real Redis + PostgreSQL clients together. Tests substitute fakes via create_app(factory)."""
from dataclasses import dataclass
from typing import Callable

import redis
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.cache import ProductCache
from app.config import Settings
from app.db import ProductRepository
from app.service import ProductService

REDIS_SOCKET_TIMEOUT_SECONDS = 2
DB_POOL_MIN_SIZE = 1
DB_POOL_MAX_SIZE = 10
DB_POOL_TIMEOUT_SECONDS = 5
DB_STARTUP_WAIT_SECONDS = 30


@dataclass
class Dependencies:
    cache: ProductCache
    repo: ProductRepository
    service: ProductService
    close: Callable[[], None]


def build_dependencies(settings: Settings) -> Dependencies:
    redis_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    pool = ConnectionPool(
        settings.database_url,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        timeout=DB_POOL_TIMEOUT_SECONDS,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=DB_STARTUP_WAIT_SECONDS)
    repo = ProductRepository(pool, settings.slow_query_ms)
    repo.ensure_seeded(settings.seed_product_count)
    cache = ProductCache(redis_client, settings.cache_ttl_seconds)

    def close() -> None:
        pool.close()
        redis_client.close()

    return Dependencies(cache=cache, repo=repo, service=ProductService(cache, repo), close=close)
