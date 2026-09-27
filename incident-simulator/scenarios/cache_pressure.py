"""Scenario: CACHE SATURATION.

Story: a deploy of the (fictional) auth-service dropped the TTL on session keys, so sessions pile
up in the shared Redis forever. Redis runs `volatile-lru`: it may only evict keys that HAVE a TTL,
i.e. product-api's cache entries. Once memory is full of immortal sessions, product entries are
evicted or rejected (OOM), every product lookup misses, and each miss pays a slow DB query.

Most injected sessions are stale (last seen 3 days ago). A few hundred belong to users who are
active right now — flushing the whole cache would log them out. That distinction is what the
human operator will teach OpsMind in the demo.

Everything is deterministic: same key names, same counts, same sizes on every run.
"""
import hashlib
import time
from dataclasses import dataclass
from itertools import islice
from typing import Callable, Iterable, Iterator

import redis

SESSION_KEY_PREFIX = "session:"
SESSION_SCAN_PATTERN = SESSION_KEY_PREFIX + "*"
ACTIVE_SESSION_COUNT = 300
SESSION_PADDING_BYTES = 1024
WRITE_BATCH_SIZE = 500
SCAN_BATCH_SIZE = 1000
# Safety cap so a Redis without a memory limit can't be filled forever.
MAX_STALE_SESSIONS = 200_000
KEY_HASH_LENGTH = 16

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
STALE_AGE_SECONDS = 72 * SECONDS_PER_HOUR
# A session not seen for this long is "stale" (used by --status and, later, RB-CACHE-001).
STALE_THRESHOLD_SECONDS = 24 * SECONDS_PER_HOUR
ACTIVE_SPREAD_MINUTES = 30


@dataclass(frozen=True)
class InjectResult:
    active_written: int
    stale_written: int
    is_saturated: bool


@dataclass(frozen=True)
class CacheStatus:
    used_bytes: int
    max_bytes: int
    evicted_keys: int
    policy: str
    active_sessions: int
    stale_sessions: int

    @property
    def utilization(self) -> float:
        return self.used_bytes / self.max_bytes if self.max_bytes else 0.0


def session_key(kind: str, index: int) -> str:
    """Deterministic, opaque key: you can't tell stale from active by the name alone."""
    digest = hashlib.sha1(f"{kind}-{index}".encode()).hexdigest()[:KEY_HASH_LENGTH]
    return SESSION_KEY_PREFIX + digest


def _session_fields(index: int, last_seen: int) -> dict:
    return {
        "user_id": f"user-{index:06d}",
        "last_seen": last_seen,
        "issued_by": "auth-service",
        "data": "x" * SESSION_PADDING_BYTES,
    }


def _chunks(items: Iterable, size: int) -> Iterator[list]:
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _write_batch(client: redis.Redis, batch: list[tuple[str, dict]]) -> tuple[int, bool]:
    """Write one pipeline of sessions (no TTL). Returns (written, is_redis_full)."""
    pipe = client.pipeline(transaction=False)
    for key, fields in batch:
        pipe.hset(key, mapping=fields)
    results = pipe.execute(raise_on_error=False)
    rejected = [r for r in results if isinstance(r, redis.ResponseError)]
    is_full = any(isinstance(r, redis.exceptions.OutOfMemoryError) for r in rejected)
    if rejected and not is_full:
        raise rejected[0]
    return len(results) - len(rejected), is_full


def _write_sessions(
    client: redis.Redis, kind: str, last_seen_for: Callable[[int], int], limit: int
) -> tuple[int, bool]:
    written = 0
    for start in range(0, limit, WRITE_BATCH_SIZE):
        indexes = range(start, min(start + WRITE_BATCH_SIZE, limit))
        batch = [(session_key(kind, i), _session_fields(i, last_seen_for(i))) for i in indexes]
        count, is_full = _write_batch(client, batch)
        written += count
        if is_full:
            return written, True
    return written, False


def inject(client: redis.Redis, now: int | None = None) -> InjectResult:
    """Write active sessions, then stale sessions until Redis refuses more (OOM)."""
    now = int(now if now is not None else time.time())

    def active_last_seen(i: int) -> int:
        return now - (i % ACTIVE_SPREAD_MINUTES) * SECONDS_PER_MINUTE

    def stale_last_seen(i: int) -> int:
        return now - STALE_AGE_SECONDS - i

    active, is_full = _write_sessions(client, "active", active_last_seen, ACTIVE_SESSION_COUNT)
    if is_full:
        return InjectResult(active, 0, True)
    stale, is_full = _write_sessions(client, "stale", stale_last_seen, MAX_STALE_SESSIONS)
    return InjectResult(active, stale, is_full)


def count_sessions(client: redis.Redis, now: int | None = None) -> tuple[int, int]:
    """Returns (active, stale) by reading each session's last_seen field."""
    now = int(now if now is not None else time.time())
    active = stale = 0
    for chunk in _chunks(client.scan_iter(match=SESSION_SCAN_PATTERN, count=SCAN_BATCH_SIZE), SCAN_BATCH_SIZE):
        pipe = client.pipeline(transaction=False)
        for key in chunk:
            pipe.hget(key, "last_seen")
        for last_seen in pipe.execute():
            if last_seen is None:
                continue
            if now - int(last_seen) >= STALE_THRESHOLD_SECONDS:
                stale += 1
            else:
                active += 1
    return active, stale


def _eviction_policy(client: redis.Redis) -> str:
    try:
        return client.config_get("maxmemory-policy").get("maxmemory-policy", "unknown")
    except redis.ResponseError:
        return "unknown"


def status(client: redis.Redis, now: int | None = None) -> CacheStatus:
    memory = client.info("memory")
    stats = client.info("stats")
    active, stale = count_sessions(client, now)
    return CacheStatus(
        used_bytes=int(memory.get("used_memory", 0)),
        max_bytes=int(memory.get("maxmemory", 0)),
        evicted_keys=int(stats.get("evicted_keys", 0)),
        policy=_eviction_policy(client),
        active_sessions=active,
        stale_sessions=stale,
    )


def restore(client: redis.Redis) -> int:
    """Test-environment reset: remove every injected session. NOT the production runbook
    (RB-CACHE-001 will remove only stale sessions)."""
    deleted = 0
    for chunk in _chunks(client.scan_iter(match=SESSION_SCAN_PATTERN, count=SCAN_BATCH_SIZE), SCAN_BATCH_SIZE):
        deleted += client.unlink(*chunk)
    return deleted
