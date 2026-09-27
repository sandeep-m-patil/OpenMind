"""Deterministic, fixed-rate ("open-loop") traffic for product-api, with a latency report.

    python load_generator.py                          # 50 req/s for 30 s
    python load_generator.py --rate 100 --duration 60

Why fixed-rate: real users keep arriving whether or not the service is slow. When capacity drops
below the arrival rate, requests queue up and latency climbs â€” that is how real incidents look.
(A "closed loop" of N users who wait for each reply would politely slow down and hide the problem.)
Latency is measured from each request's *scheduled* send time, so queueing delay is included.
The product-id sequence comes from a seeded generator, so every run sends the same requests.
"""
import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first, Docker only
# publishes on IPv4, and every new connection then stalls ~2 s before falling back.
DEFAULT_API_URL = "http://127.0.0.1:8001"
DEFAULT_DURATION_SECONDS = 30
# Healthy capacity is ~200 req/s; saturated-cache capacity is ~40 req/s. 50 sits between,
# so the incident builds a queue (seconds of latency) while normal operation stays idle-fast.
DEFAULT_RATE_PER_SECOND = 50
DEFAULT_SEED = 42
MAX_IN_FLIGHT = 200
WARMUP_CONCURRENCY = 20
PRODUCT_ID_MIN = 1
PRODUCT_ID_MAX = 500  # product-api seeds 500 products
REQUEST_TIMEOUT_SECONDS = 15
HTTP_SERVER_ERROR = 500
MS_PER_SECOND = 1000
PERCENT = 100
REPORTED_PERCENTILES = (50, 95, 99)


@dataclass(frozen=True)
class LoadOptions:
    api_url: str = DEFAULT_API_URL
    duration_seconds: float = DEFAULT_DURATION_SECONDS
    rate_per_second: float = DEFAULT_RATE_PER_SECOND
    seed: int = DEFAULT_SEED
    transport: httpx.BaseTransport | None = None  # tests inject a mock transport


@dataclass(frozen=True)
class Sample:
    latency_ms: float
    is_error: bool
    cache: str | None


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile; 0.0 for no data."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, round(pct / PERCENT * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _request(client: httpx.Client, product_id: int, scheduled_at: float | None = None) -> Sample:
    start = scheduled_at if scheduled_at is not None else time.perf_counter()
    try:
        response = client.get(f"/products/{product_id}")
        is_error, cache = response.status_code >= HTTP_SERVER_ERROR, response.headers.get("x-cache")
    except httpx.HTTPError:
        is_error, cache = True, None
    return Sample((time.perf_counter() - start) * MS_PER_SECOND, is_error, cache)


def _client(options: LoadOptions) -> httpx.Client:
    """One thread-safe client shared by all threads. (Creating a client is slow on Windows â€”
    it loads the TLS bundle â€” so one per thread would distort the measurement.)"""
    limits = httpx.Limits(max_connections=MAX_IN_FLIGHT, max_keepalive_connections=MAX_IN_FLIGHT)
    return httpx.Client(
        base_url=options.api_url, timeout=REQUEST_TIMEOUT_SECONDS, limits=limits, transport=options.transport
    )


def warm_up(options: LoadOptions) -> None:
    """Touch every product once so a healthy cache starts full (not measured)."""
    with _client(options) as client, ThreadPoolExecutor(WARMUP_CONCURRENCY) as pool:
        list(pool.map(lambda pid: _request(client, pid), range(PRODUCT_ID_MIN, PRODUCT_ID_MAX + 1)))


def run_load(options: LoadOptions) -> list[Sample]:
    """Send requests on a fixed schedule, regardless of how fast replies come back."""
    rng = random.Random(options.seed)
    interval = 1 / options.rate_per_second
    total = int(options.rate_per_second * options.duration_seconds)
    with _client(options) as client, ThreadPoolExecutor(MAX_IN_FLIGHT) as pool:
        start = time.perf_counter()
        futures = []
        for i in range(total):
            scheduled_at = start + i * interval
            time.sleep(max(0.0, scheduled_at - time.perf_counter()))
            product_id = rng.randint(PRODUCT_ID_MIN, PRODUCT_ID_MAX)
            futures.append(pool.submit(_request, client, product_id, scheduled_at))
        return [future.result() for future in futures]


def summarize(samples: list[Sample], elapsed_seconds: float) -> dict:
    latencies = [s.latency_ms for s in samples]
    errors = sum(s.is_error for s in samples)
    hits = sum(s.cache == "HIT" for s in samples)
    total = len(samples)
    return {
        "requests": total,
        "rps": total / elapsed_seconds if elapsed_seconds else 0.0,
        "error_rate": errors / total if total else 0.0,
        "hit_ratio": hits / total if total else 0.0,
        **{f"p{p}_ms": percentile(latencies, p) for p in REPORTED_PERCENTILES},
    }


def _print_report(report: dict) -> None:
    print(
        f"  requests  : {report['requests']} completed ({report['rps']:.1f} req/s incl. drain)\n"
        f"  errors    : {report['error_rate'] * PERCENT:.1f}%\n"
        f"  latency   : p50 {report['p50_ms']:.0f} ms | p95 {report['p95_ms']:.0f} ms | p99 {report['p99_ms']:.0f} ms\n"
        f"  cache hit : {report['hit_ratio'] * PERCENT:.1f}%"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic fixed-rate load for product-api")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_SECONDS, help="seconds")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_PER_SECOND, help="requests per second")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-warmup", action="store_true", help="skip the cache warm-up pass")
    args = parser.parse_args(argv)
    if args.rate <= 0 or args.duration <= 0:
        parser.error("--rate and --duration must be positive")
    options = LoadOptions(args.api_url, args.duration, args.rate, args.seed)

    if not args.no_warmup:
        print("Warming cache (all products once)...")
        warm_up(options)
    print(f"Sending {options.rate_per_second:.0f} req/s for {options.duration_seconds:.0f}s...")
    start = time.perf_counter()
    samples = run_load(options)
    _print_report(summarize(samples, time.perf_counter() - start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
