"""RB-CACHE-002: FLUSHDB on the product-api Redis database (HIGH risk). Requires --dry-run or --apply."""
import argparse
import json
import sys

import redis


def flush(client: redis.Redis, is_dry_run: bool) -> dict:
    keys_before = client.dbsize()
    if not is_dry_run:
        client.flushdb()
    return {
        "action": "full_cache_flush",
        "dry_run": is_dry_run,
        "keys_before": keys_before,
        "keys_deleted": 0 if is_dry_run else keys_before,
        "keys_after": client.dbsize(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--result-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    client = redis.Redis.from_url(args.redis_url, decode_responses=True, socket_timeout=10)
    report = flush(client, args.dry_run)
    with open(args.result_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
