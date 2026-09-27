"""Pure verification logic: did the real metrics recover? (Exit code 0 is never enough.)"""
from dataclasses import asdict, dataclass

MIN_IMPROVEMENT_RATIO = 0.5  # P95 must at least halve
MIN_CACHE_HIT_RATIO = 0.8


@dataclass
class Verdict:
    is_resolved: bool
    has_data: bool
    checks: dict[str, bool]
    p95_before: float | None
    p95_after: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate(before: dict, after: dict, health: dict, p95_target: float, category: str | None) -> Verdict:
    p95_before, p95_after = before.get("p95_seconds"), after.get("p95_seconds")
    if p95_after is None:
        return Verdict(False, False, {}, p95_before, None)
    checks = {
        "p95_below_target": p95_after <= p95_target,
        "p95_improved": p95_before is None or p95_after <= p95_before * MIN_IMPROVEMENT_RATIO,
        "service_healthy": health.get("status") == "ok",
    }
    if category == "cache_saturation" and after.get("cache_hit_ratio") is not None:
        checks["cache_hit_ratio_recovered"] = after["cache_hit_ratio"] >= MIN_CACHE_HIT_RATIO
    return Verdict(all(checks.values()), True, checks, p95_before, p95_after)
