import logging

import redis

from app.cache import MemoryStats, ProductCache
from app.metrics import REDIS_MEMORY_UTILIZATION, REDIS_UP, refresh_redis_gauges

TTL_SECONDS = 60
MEGABYTE = 1024 * 1024


class BrokenRedis:
    """Every command fails, like a Redis that has gone away."""

    def __getattr__(self, _name):
        def fail(*_args, **_kwargs):
            raise redis.ConnectionError("redis is down")

        return fail


class StatsRedis:
    def __init__(self, used_bytes: int, max_bytes: int, evicted: int) -> None:
        self._memory = {"used_memory": used_bytes, "maxmemory": max_bytes}
        self._stats = {"evicted_keys": evicted}

    def info(self, section: str) -> dict:
        return self._memory if section == "memory" else self._stats


def test_values_round_trip_as_json(fake_redis):
    cache = ProductCache(fake_redis, TTL_SECONDS)

    cache.set_json("k", {"a": 1})

    assert cache.get_json("k") == {"a": 1}


def test_values_expire_after_ttl(fake_redis):
    ProductCache(fake_redis, TTL_SECONDS).set_json("k", 1)

    assert fake_redis.ttl("k") == TTL_SECONDS


def test_redis_outage_degrades_to_miss_instead_of_raising():
    cache = ProductCache(BrokenRedis(), TTL_SECONDS)
    cache.set_json("k", 1)

    assert (cache.get_json("k"), cache.ping(), cache.memory_stats()) == (None, False, None)


def test_utilization_is_used_over_max():
    assert MemoryStats(used_bytes=24, max_bytes=32, evicted_keys=0).utilization == 0.75


def test_utilization_is_zero_when_maxmemory_is_unlimited():
    assert MemoryStats(used_bytes=24, max_bytes=0, evicted_keys=0).utilization == 0.0


def test_memory_stats_read_from_redis_info():
    cache = ProductCache(StatsRedis(8 * MEGABYTE, 32 * MEGABYTE, evicted=7), TTL_SECONDS)

    assert cache.memory_stats() == MemoryStats(8 * MEGABYTE, 32 * MEGABYTE, 7)


def test_refresh_warns_on_cache_pressure(caplog):
    cache = ProductCache(StatsRedis(31 * MEGABYTE, 32 * MEGABYTE, evicted=500), TTL_SECONDS)

    with caplog.at_level(logging.WARNING):
        refresh_redis_gauges(cache, warn_ratio=0.9)

    assert [r.event for r in caplog.records] == ["cache_pressure"]
    assert REDIS_MEMORY_UTILIZATION._value.get() == 31 / 32


def test_refresh_marks_redis_down_when_stats_unavailable():
    refresh_redis_gauges(ProductCache(BrokenRedis(), TTL_SECONDS), warn_ratio=0.9)

    assert REDIS_UP._value.get() == 0
