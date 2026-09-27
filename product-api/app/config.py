"""Runtime settings for product-api, read once from environment variables."""
import os
from dataclasses import dataclass

DEFAULT_CACHE_TTL_SECONDS = 300
# Simulated cost of a cache miss (stands in for an expensive join/aggregation).
DEFAULT_SLOW_QUERY_MS = 250
# Requests slower than this are logged at WARNING.
DEFAULT_SLOW_REQUEST_MS = 500
# Redis memory utilization at/above this ratio is logged as cache pressure.
DEFAULT_MEMORY_WARN_RATIO = 0.90
DEFAULT_SEED_PRODUCT_COUNT = 500


@dataclass(frozen=True)
class Settings:
    service_name: str
    log_level: str
    redis_url: str
    database_url: str
    cache_ttl_seconds: int
    slow_query_ms: int
    slow_request_ms: int
    memory_warn_ratio: float
    seed_product_count: int


def load_settings() -> Settings:
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "product-api"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        database_url=os.getenv("DATABASE_URL", "postgresql://localhost:5432/shop"),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)),
        slow_query_ms=int(os.getenv("SLOW_QUERY_MS", DEFAULT_SLOW_QUERY_MS)),
        slow_request_ms=int(os.getenv("SLOW_REQUEST_MS", DEFAULT_SLOW_REQUEST_MS)),
        memory_warn_ratio=float(os.getenv("MEMORY_WARN_RATIO", DEFAULT_MEMORY_WARN_RATIO)),
        seed_product_count=int(os.getenv("SEED_PRODUCT_COUNT", DEFAULT_SEED_PRODUCT_COUNT)),
    )
