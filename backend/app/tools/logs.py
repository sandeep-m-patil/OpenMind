"""get_logs(): summarize product-api's structured JSON log file for a recent time window."""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

TAIL_BYTES = 4 * 1024 * 1024  # read at most the last 4 MB — plenty for a 5-minute window
MAX_SAMPLES = 5
TOP_MESSAGES = 8
NOTABLE_LEVELS = {"WARNING", "ERROR", "CRITICAL"}


def _read_tail(path: str) -> list[str]:
    with open(path, "rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - TAIL_BYTES))
        chunk = handle.read().decode("utf-8", errors="replace")
    lines = chunk.splitlines()
    return lines[1:] if size > TAIL_BYTES else lines  # first line may be cut in half


def _parse(line: str) -> dict | None:
    try:
        record = json.loads(line)
        record["_ts"] = datetime.fromisoformat(record["ts"])
        return record
    except (ValueError, KeyError, TypeError):
        return None


def summarize_logs(path: str, window_minutes: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(minutes=window_minutes)
    records = [r for r in (_parse(line) for line in _read_tail(path)) if r and r["_ts"] >= since]
    levels = Counter(r.get("level", "?") for r in records)
    notable = [r for r in records if r.get("level") in NOTABLE_LEVELS]
    messages = Counter(f"{r.get('level')}: {r.get('msg')}" for r in notable)
    samples = [{k: v for k, v in r.items() if not k.startswith("_")} for r in notable[-MAX_SAMPLES:]]
    slow = [r["duration_ms"] for r in records if r.get("event") == "http_request" and "duration_ms" in r]
    return {
        "window_minutes": window_minutes,
        "total_lines": len(records),
        "by_level": dict(levels),
        "top_warnings": [{"message": m, "count": c} for m, c in messages.most_common(TOP_MESSAGES)],
        "samples": samples,
        "max_request_ms": max(slow) if slow else None,
    }
