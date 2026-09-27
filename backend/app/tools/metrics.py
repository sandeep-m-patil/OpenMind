"""get_metrics(): a snapshot of product-api health from Prometheus (deterministic numbers only)."""
import math

import httpx

QUERY_TIMEOUT_SECONDS = 5
ROUTE = 'job="product-api", path="/products/{product_id}"'
JOB = 'job="product-api"'
BASELINE_LOOKBACK = "30m"
BASELINE_STEP = "30s"


def _latency(quantile: float, window: str) -> str:
    return f"histogram_quantile({quantile}, sum by (le) (rate(http_request_duration_seconds_bucket{{{ROUTE}}}[{window}])))"


def build_queries(window: str) -> dict[str, str]:
    hits = f"sum(rate(cache_hits_total{{{JOB}}}[{window}]))"
    misses = f"sum(rate(cache_misses_total{{{JOB}}}[{window}]))"
    return {
        "p50_seconds": _latency(0.5, window),
        "p95_seconds": _latency(0.95, window),
        "p99_seconds": _latency(0.99, window),
        # Lowest 1-minute P95 in the last 30 minutes ≈ "normal" latency before the incident.
        "baseline_p95_seconds": f"min_over_time(({_latency(0.95, '1m')})[{BASELINE_LOOKBACK}:{BASELINE_STEP}])",
        "request_rate": f"sum(rate(http_requests_total{{{JOB}}}[{window}]))",
        "error_rate": f"sum(rate(http_request_errors_total{{{JOB}}}[{window}])) / sum(rate(http_requests_total{{{JOB}}}[{window}]))",
        "cache_hit_ratio": f"{hits} / ({hits} + {misses})",
        "redis_memory_utilization": f"max(redis_memory_utilization_ratio{{{JOB}}})",
        "redis_evictions_per_second": f"sum(rate(redis_evicted_keys{{{JOB}}}[{window}]))",
        "redis_up": f"max(redis_up{{{JOB}}})",
    }


class PrometheusClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=QUERY_TIMEOUT_SECONDS, transport=transport)

    def query_scalar(self, expr: str) -> float | None:
        """First sample of an instant query, or None when there is no data (e.g. no traffic)."""
        response = self._client.get("/api/v1/query", params={"query": expr})
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise RuntimeError(f"prometheus error: {body.get('error')}")
        results = body["data"]["result"]
        if not results:
            return None
        value = float(results[0]["value"][1])
        return None if math.isnan(value) or math.isinf(value) else value

    def snapshot(self, window: str = "1m") -> dict[str, float | None]:
        return {name: self.query_scalar(expr) for name, expr in build_queries(window).items()}

    def is_reachable(self) -> bool:
        try:
            return self._client.get("/-/ready").status_code == httpx.codes.OK
        except httpx.HTTPError:
            return False
