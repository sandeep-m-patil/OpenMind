"""Create, inspect, or undo a deterministic incident in the local OpsMind environment.

    python create_incident.py --type cache             # inject cache saturation
    python create_incident.py --type cache --status    # show cache / session state
    python create_incident.py --type cache --restore   # remove injected data (reset)
"""
import argparse
import os
import sys

import httpx
import redis

from scenarios import cache_pressure

DEFAULT_REDIS_URL = "redis://127.0.0.1:6380/0"  # 127.0.0.1 avoids the Windows IPv6 stall
DEFAULT_OPSMIND_URL = "http://127.0.0.1:8002"
REDIS_TIMEOUT_SECONDS = 5
EXPECTED_POLICY = "volatile-lru"
EXIT_OK = 0
EXIT_UNAVAILABLE = 2
BYTES_PER_MB = 1024 * 1024
PERCENT = 100


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpsMind deterministic incident simulator")
    parser.add_argument("--type", required=True, choices=["cache"], help="incident scenario")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="show current state only")
    action.add_argument("--restore", action="store_true", help="undo the incident")
    parser.add_argument(
        "--redis-url",
        default=os.getenv("SIMULATOR_REDIS_URL", DEFAULT_REDIS_URL),
        help=f"Redis to target (default: {DEFAULT_REDIS_URL})",
    )
    parser.add_argument("--opsmind-url", default=os.getenv("OPSMIND_URL", DEFAULT_OPSMIND_URL),
                        help="OpsMind backend, to record the story's deployment event")
    parser.add_argument("--no-deploy-event", action="store_true", help="don't record the auth-service deploy")
    return parser.parse_args(argv)


def _record_deploy_event(opsmind_url: str) -> None:
    """Best effort: tell OpsMind about the deploy that 'caused' the incident (for correlation)."""
    try:
        httpx.post(f"{opsmind_url}/v1/deployments", json=cache_pressure.DEPLOY_EVENT,
                   timeout=REDIS_TIMEOUT_SECONDS).raise_for_status()
        event = cache_pressure.DEPLOY_EVENT
        print(f"Recorded deployment {event['service']} {event['version']} in OpsMind.")
    except httpx.HTTPError as exc:
        print(f"  NOTE: could not record deployment in OpsMind ({exc}); continuing.")


def _print_status(state: cache_pressure.CacheStatus) -> None:
    print(
        f"  redis memory : {state.used_bytes / BYTES_PER_MB:.1f} MB / {state.max_bytes / BYTES_PER_MB:.1f} MB"
        f"  ({state.utilization * PERCENT:.1f}%)\n"
        f"  evicted keys : {state.evicted_keys}\n"
        f"  policy       : {state.policy}\n"
        f"  sessions     : {state.active_sessions} active, {state.stale_sessions} stale"
    )
    if state.policy not in (EXPECTED_POLICY, "unknown"):
        print(
            f"  WARNING: policy is {state.policy}, expected {EXPECTED_POLICY}. The incident will not\n"
            "  reproduce. Recreate Redis:  docker compose up -d --force-recreate redis"
        )


def _run(client: redis.Redis, args: argparse.Namespace) -> None:
    if args.status:
        print("Cache status:")
    elif args.restore:
        deleted = cache_pressure.restore(client)
        print(f"Restored: removed {deleted} injected session keys.")
    else:
        if not args.no_deploy_event:
            _record_deploy_event(args.opsmind_url)
        result = cache_pressure.inject(client)
        print(
            f"Injected cache saturation: {result.active_written} active + "
            f"{result.stale_written} stale sessions (no TTL)."
        )
        if not result.is_saturated:
            print("  NOTE: Redis never filled up — is maxmemory set? Incident may be weak.")
    _print_status(cache_pressure.status(client))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    client = redis.Redis.from_url(
        args.redis_url, decode_responses=True, socket_timeout=REDIS_TIMEOUT_SECONDS
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        print(
            f"Cannot reach Redis at {args.redis_url}: {exc}\n"
            "Is the stack running?  docker compose ps",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE
    _run(client, args)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
