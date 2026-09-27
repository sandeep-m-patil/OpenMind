"""Reset OpsMind to a blank slate for a fresh demo: no incidents, no learned memory, no scores.

    python reset_demo.py --yes

Deletes (irreversibly): all OpsMind incidents, deployments, strategy scores and workflow checkpoints,
and every memory in the Hindsight bank. Also removes any injected sessions from Redis.
"""
import argparse
import os
import subprocess
import sys

import httpx
import redis

from scenarios import cache_pressure

DEFAULT_HINDSIGHT_URL = "http://127.0.0.1:8888"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6380/0"
REQUEST_TIMEOUT_SECONDS = 30
# Fixed statement — no user input is interpolated.
RESET_SQL = (
    "TRUNCATE incidents, deployments, strategy_stats; "
    "ALTER SEQUENCE incident_number_seq RESTART WITH 1001; "
    "DO $$ BEGIN IF to_regclass('checkpoints') IS NOT NULL THEN "
    "TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes; END IF; END $$;"
)


def reset_database(compose_file: str, db_user: str) -> None:
    command = ["docker", "compose", "-f", compose_file, "exec", "-T", "postgres",
               "psql", "-U", db_user, "-d", "opsmind", "-v", "ON_ERROR_STOP=1", "-c", RESET_SQL]
    subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603 — fixed argv


def reset_memory(hindsight_url: str, bank: str) -> None:
    response = httpx.delete(f"{hindsight_url}/v1/default/banks/{bank}/memories", timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code not in (httpx.codes.OK, httpx.codes.NOT_FOUND):
        response.raise_for_status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="confirm: permanently delete demo history")
    parser.add_argument("--compose-file", default=os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml"))
    parser.add_argument("--db-user", default=os.getenv("POSTGRES_USER", "opsmind"))
    parser.add_argument("--hindsight-url", default=os.getenv("HINDSIGHT_URL", DEFAULT_HINDSIGHT_URL))
    parser.add_argument("--bank", default=os.getenv("HINDSIGHT_BANK", "opsmind-sre"))
    parser.add_argument("--redis-url", default=os.getenv("SIMULATOR_REDIS_URL", DEFAULT_REDIS_URL))
    args = parser.parse_args(argv)
    if not args.yes:
        print("Refusing to reset without --yes (this permanently deletes incidents and learned memory).")
        return 1
    removed = cache_pressure.restore(redis.Redis.from_url(args.redis_url, decode_responses=True))
    print(f"Redis: removed {removed} injected session keys.")
    reset_database(args.compose_file, args.db_user)
    print("OpsMind: incidents, deployments, strategy scores and checkpoints cleared (next incident is INC-1001).")
    reset_memory(args.hindsight_url, args.bank)
    print(f"Hindsight: all memories in bank '{args.bank}' cleared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
