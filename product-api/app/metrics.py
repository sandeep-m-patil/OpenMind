"""Prometheus metrics exposed on GET /metrics."""
import logging

from prometheus_client import Counter, Gauge, Histogram

# Fine-grained around the 150 ms "normal" P95, coarse up to 10 s for incidents.
LATENCY_BUCKETS_SECONDS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "path", "status"])
ERRORS = Counter("http_request_errors_total", "HTTP requests that returned 5xx", ["method", "path"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=LATENCY_BUCKETS_SECONDS,
)
CACHE_HITS = Counter("cache_hits_total", "Product cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Product cache misses")

REDIS_UP = Gauge("redis_up", "1 if Redis answered the last stats query, else 0")
REDIS_MEMORY_USED = Gauge("redis_memory_used_bytes", "Redis used_memory")
REDIS_MEMORY_MAX = Gauge("redis_memory_max_bytes", "Redis maxmemory (0 = unlimited)")
REDIS_MEMORY_UTILIZATION = Gauge("redis_memory_utilization_ratio", "used_memory / maxmemory")
REDIS_EVICTED_KEYS = Gauge("redis_evicted_keys", "Keys evicted by Redis since it started")

logger = logging.getLogger("product_api.metrics")


def refresh_redis_gauges(cache, warn_ratio: float) -> None:
    """Pull fresh Redis stats into gauges; log a warning when the cache is under pressure."""
    stats = cache.memory_stats()
    if stats is None:
        REDIS_UP.set(0)
        return
    REDIS_UP.set(1)
    REDIS_MEMORY_USED.set(stats.used_bytes)
    REDIS_MEMORY_MAX.set(stats.max_bytes)
    REDIS_MEMORY_UTILIZATION.set(stats.utilization)
    REDIS_EVICTED_KEYS.set(stats.evicted_keys)
    if stats.utilization >= warn_ratio:
        logger.warning(
            "redis memory pressure",
            extra={
                "event": "cache_pressure",
                "redis_memory_utilization": round(stats.utilization, 3),
                "evicted_keys": stats.evicted_keys,
            },
        )
