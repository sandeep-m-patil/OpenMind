"""Thin Redis wrapper. Redis failures degrade to cache misses instead of failing requests."""
import json
import logging
from dataclasses import dataclass
from typing import Any

import redis

logger = logging.getLogger("product_api.cache")


@dataclass(frozen=True)
class MemoryStats:
    used_bytes: int
    max_bytes: int
    evicted_keys: int

    @property
    def utilization(self) -> float:
        return self.used_bytes / self.max_bytes if self.max_bytes else 0.0


class ProductCache:
    def __init__(self, client: redis.Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except redis.RedisError:
            logger.error("cache read failed", extra={"event": "cache_error", "key": key}, exc_info=True)
            return None
        return json.loads(raw) if raw is not None else None

    def set_json(self, key: str, value: Any) -> None:
        try:
            self._client.set(key, json.dumps(value), ex=self._ttl_seconds)
        except redis.RedisError as exc:
            # Expected under cache saturation (Redis replies "OOM command not allowed..."):
            # one compact line per failure, no traceback, so logs stay readable evidence.
            logger.warning(
                "cache write rejected",
                extra={"event": "cache_write_rejected", "key": key, "error": str(exc)},
            )

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except redis.RedisError:
            return False

    def memory_stats(self) -> MemoryStats | None:
        try:
            memory = self._client.info("memory")
            stats = self._client.info("stats")
        except redis.RedisError:
            return None
        return MemoryStats(
            used_bytes=int(memory.get("used_memory", 0)),
            max_bytes=int(memory.get("maxmemory", 0)),
            evicted_keys=int(stats.get("evicted_keys", 0)),
        )
