"""RB-CACHE-001: delete session:* hashes whose last_seen is older than --max-idle-hours.

Active sessions and every non-session key (e.g. product:* cache entries) are left alone.
Requires an explicit --dry-run or --apply.
"""
import argparse
import json
import sys
import time
from itertools import islice

import redis

SESSION_PATTERN = "session:*"
SCAN_COUNT = 1000
BATCH_SIZE = 1000
SECONDS_PER_HOUR = 3600


def _batches(iterator, size):
    while batch := list(islice(iterator, size)):
        yield batch


def cleanup(client: redis.Redis, max_idle_hours: int, is_dry_run: bool, now: float) -> dict:
    cutoff = now - max_idle_hours * SECONDS_PER_HOUR
    scanned = stale = deleted = 0
    for batch in _batches(client.scan_iter(match=SESSION_PATTERN, count=SCAN_COUNT), BATCH_SIZE):
        pipe = client.pipeline(transaction=False)
        for key in batch:
            pipe.hget(key, "last_seen")
        stale_keys = [k for k, seen in zip(batch, pipe.execute()) if seen is not None and float(seen) < cutoff]
        scanned += len(batch)
        stale += len(stale_keys)
        if stale_keys and not is_dry_run:
            deleted += client.unlink(*stale_keys)
    memory = client.info("memory")
    return {
        "action": "targeted_stale_session_cleanup",
        "dry_run": is_dry_run,
        "max_idle_hours": max_idle_hours,
        "sessions_scanned": scanned,
        "sessions_stale": stale,
        "sessions_deleted": deleted,
        "sessions_kept": scanned - (stale if is_dry_run else deleted),
        "redis_used_bytes_after": int(memory.get("used_memory", 0)),
        "redis_max_bytes": int(memory.get("maxmemory", 0)),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--max-idle-hours", type=int, required=True)
    parser.add_argument("--result-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    client = redis.Redis.from_url(args.redis_url, decode_responses=True, socket_timeout=10)
    report = cleanup(client, args.max_idle_hours, args.dry_run, time.time())
    with open(args.result_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
