"""Deterministic evidence analysis: thresholds and arithmetic, no LLM.

Turns raw metrics/logs/deployments into (a) boolean signals and (b) human-readable findings such as
"Redis memory reached 100%" or "auth-service was deployed 7 min before the alert".
"""
from datetime import datetime, timezone

MS_PER_SECOND = 1000
PERCENT = 100
SECONDS_PER_MINUTE = 60
HIGH_P95_SECONDS = 1.0
REDIS_SATURATED_RATIO = 0.95
LOW_HIT_RATIO = 0.5
HIGH_ERROR_RATE = 0.05
RECENT_DEPLOY_MINUTES = 30
CACHE_REJECT_MARKER = "cache write rejected"


def _ms(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    return f"{seconds:.1f} s" if seconds >= 1 else f"{seconds * MS_PER_SECOND:.0f} ms"


def _warning_count(logs: dict, marker: str) -> int:
    return sum(w["count"] for w in logs.get("top_warnings", []) if marker in w["message"])


def compute_signals(metrics: dict, logs: dict, health: dict, changes: list[dict]) -> dict:
    p95, util, hit = metrics.get("p95_seconds"), metrics.get("redis_memory_utilization"), metrics.get("cache_hit_ratio")
    err = metrics.get("error_rate")
    return {
        "is_latency_high": p95 is not None and p95 >= HIGH_P95_SECONDS,
        "is_redis_saturated": util is not None and util >= REDIS_SATURATED_RATIO,
        "is_hit_ratio_low": hit is not None and hit < LOW_HIT_RATIO,
        "is_error_rate_high": err is not None and err >= HIGH_ERROR_RATE,
        "is_service_unhealthy": health.get("status") not in (None, "ok"),
        "cache_write_rejections": _warning_count(logs, CACHE_REJECT_MARKER),
        "has_recent_deployment": any(_minutes_ago(c) <= RECENT_DEPLOY_MINUTES for c in changes),
    }


def _minutes_ago(change: dict, now: datetime | None = None) -> float:
    deployed = change["deployed_at"]
    if isinstance(deployed, str):
        deployed = datetime.fromisoformat(deployed)
    return ((now or datetime.now(timezone.utc)) - deployed).total_seconds() / SECONDS_PER_MINUTE


def _latency_finding(metrics: dict) -> str | None:
    p95, base = metrics.get("p95_seconds"), metrics.get("baseline_p95_seconds")
    if p95 is None:
        return None
    if base:
        return f"P95 latency is {_ms(p95)} vs a baseline of {_ms(base)} ({p95 / base:.0f}× higher)."
    return f"P95 latency is {_ms(p95)}."


def build_findings(metrics: dict, logs: dict, health: dict, changes: list[dict]) -> list[str]:
    findings = [f for f in [_latency_finding(metrics)] if f]
    util, hit, evict = metrics.get("redis_memory_utilization"), metrics.get("cache_hit_ratio"), metrics.get("redis_evictions_per_second")
    if util is not None:
        findings.append(f"Redis memory is at {util * PERCENT:.0f}% of its limit.")
    if hit is not None:
        findings.append(f"Cache hit ratio is {hit * PERCENT:.0f}%.")
    if evict:
        findings.append(f"Redis is evicting {evict:.1f} keys/s.")
    rejected = _warning_count(logs, CACHE_REJECT_MARKER)
    if rejected:
        findings.append(f"{rejected} 'cache write rejected' warnings (Redis maxmemory) in the last {logs.get('window_minutes')} min.")
    if metrics.get("error_rate"):
        findings.append(f"HTTP 5xx error rate is {metrics['error_rate'] * PERCENT:.1f}%.")
    findings.append(f"Service health: {health.get('status', 'unknown')}.")
    for change in changes[:3]:
        findings.append(f"{change['service']} {change['version']} was deployed {_minutes_ago(change):.0f} min ago"
                        f" ({change.get('description') or 'no description'}).")
    return findings


def memory_query(service: str, title: str, signals: dict) -> str:
    """Natural-language recall query built from what we observed (not from a diagnosis)."""
    parts = [f"{service} incident: {title}"]
    if signals.get("is_redis_saturated"):
        parts.append("Redis memory saturated, cache evictions")
    if signals.get("is_hit_ratio_low"):
        parts.append("low cache hit ratio")
    if signals.get("is_error_rate_high"):
        parts.append("high error rate")
    if signals.get("has_recent_deployment"):
        parts.append("recent deployment")
    parts.append("What was the root cause, which remediation worked or failed, and what did the operator decide?")
    return ". ".join(parts)
