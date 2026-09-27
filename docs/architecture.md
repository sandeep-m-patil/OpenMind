# OpsMind Architecture

## The big picture (target)

```
Developer → GitHub → Jenkins → product-api (local "production")
                                   │
                         Prometheus / JSON logs
                                   │ alert
                                   ▼
                     OpsMind orchestrator (FastAPI + LangGraph)
   Intake → Evidence → Hindsight RECALL → Diagnosis → Runbook plan → Risk/policy gate
                                                                        │
                                                   Slack: Approve / Edit / Reject / Manual
                                                                        │
                        Controlled execution (runbook ID → Ansible / Jenkins)
                                                                        │
                                Verification (real metrics, before vs after)
                                                                        │
                                  Postmortem → Hindsight RETAIN → next incident is smarter
```

**Safety principle:** the LLM never produces shell commands. It chooses among pre-approved runbook
IDs (e.g. `RB-CACHE-001`); the backend loads the vetted runbook, a human approves it, and only then
does a controlled tool execute it. Success is declared from metrics, never from an exit code.

**LLM budget principle:** deterministic code does thresholds, math, validation, risk checks,
runbook lookup, execution and verification. The LLM is used only to interpret evidence, rank
causes, pick among valid runbooks and write human-readable explanations — with structured output.

## What exists today (Phase 1)

```
            ┌──────────────── docker compose (project "opsmind") ────────────────┐
 host:8001 ─┤ product-api (FastAPI, uvicorn)                                      │
            │   GET /products/{id} ──► Redis  (HIT → ~3 ms)                        │
            │                    └──► PostgreSQL (MISS → ~250 ms + cache fill)     │
            │   GET /metrics  → Prometheus text format                            │
            │   stdout        → one JSON log line per event                       │
 host:6380 ─┤ redis:7.4  maxmemory 32mb, volatile-lru                              │
 host:5433 ─┤ postgres:16  products table (500 deterministic rows)                 │
            └─────────────────────────────────────────────────────────────────────┘
```

### Why it is built this way

- **Cache-aside with an expensive miss.** Every miss pays `SLOW_QUERY_MS` in PostgreSQL. When the
  cache fills up with junk and evicts product keys, the hit rate drops and latency climbs — a real,
  causal chain the AI can reason about (not a fake `sleep` in the handler).
- **Small Redis (32 MB, `volatile-lru`).** Only keys *with* a TTL may be evicted. Product cache
  entries have a TTL; the buggy sessions injected in Phase 2 do not — so when memory fills, Redis
  can only throw away the product cache. (With `allkeys-lru` Redis would evict the unused junk
  first and there would be no incident.)
- **Bounded metric labels.** Latency is labelled by route template (`/products/{product_id}`),
  not by raw URL, so Prometheus doesn't blow up.
- **Redis failures degrade, not crash.** If Redis dies, requests become misses and `/health`
  reports `degraded` (503) — useful evidence later.

### product-api modules

| File | Responsibility |
|---|---|
| `config.py` | All settings from env vars, with named defaults |
| `cache.py` | Redis get/set JSON, ping, memory stats (`INFO memory`/`INFO stats`) |
| `db.py` | Schema, deterministic seed, parameterized queries, simulated query cost |
| `service.py` | Cache-aside logic + hit/miss counters |
| `metrics.py` | Prometheus metric definitions; refresh Redis gauges; cache-pressure warning |
| `middleware.py` | Per-request metrics + structured request log |
| `logging_setup.py` | JSON log formatter |
| `dependencies.py` | Wires real clients (tests inject fakes instead) |
| `main.py` | Routes, `{data, meta, error}` envelope, error handlers |

### Metrics exposed

| Metric | Type | Meaning |
|---|---|---|
| `http_requests_total{method,path,status}` | counter | request rate |
| `http_request_errors_total{method,path}` | counter | 5xx rate |
| `http_request_duration_seconds{method,path}` | histogram | latency (P95 via `histogram_quantile`) |
| `cache_hits_total` / `cache_misses_total` | counter | cache hit ratio |
| `redis_memory_used_bytes` / `redis_memory_max_bytes` | gauge | cache size |
| `redis_memory_utilization_ratio` | gauge | used / max (0–1) |
| `redis_evicted_keys` | gauge | keys evicted since Redis started |
| `redis_up` | gauge | 1 if Redis answered |

## Incident simulator (Phase 2)

### Scenario `cache` — cache saturation

```
auth-service deploy drops session TTL  (the "bug" — story for Phase 11's deploy correlation)
        │
        ▼
~19,000 immortal session:* hashes (≈1 KB each) fill Redis to 100%
   ├─ 300 are ACTIVE   (last_seen < 30 min)   ← flushing everything would log these users out
   └─ rest are STALE   (last_seen ≈ 3 days)   ← safe to delete (RB-CACHE-001, Phase 7)
        │  volatile-lru can only evict keys with a TTL = product cache
        ▼
product:* keys evicted / SET rejected with OOM  →  hit ratio 100% → ~5%
        │  every miss = 250 ms DB query, DB pool = 10 connections → capacity ≈ 40 req/s
        ▼
arrivals (50 req/s) > capacity  →  queue grows  →  p95 ≈ 13 ms → ≈ 7 s
```

Evidence the app emits (what OpsMind will later collect):
- metrics: `redis_memory_utilization_ratio` ≈ 1.0, `redis_evicted_keys` rising,
  `cache_misses_total` rate up, `http_request_duration_seconds` P95 up
- logs: `cache write rejected` (`error: command not allowed when used memory > 'maxmemory'`),
  `slow request` warnings, `redis memory pressure` on each metrics scrape

**Determinism:** key names are hashes of `(kind, index)`; counts and sizes are constants; the load
generator's product-id sequence is seeded. The stale-session count varies by a few dozen between runs
(Redis internal memory overhead) — the effect does not.

**`--restore` vs the runbook:** `--restore` is a *test-environment reset* and deletes every injected
session. The production remediation (RB-CACHE-001) will delete only stale ones — that difference is the
human correction OpsMind learns in the demo.

### Load generator — why fixed-rate

A closed loop of N users that wait for each reply slows down when the server does, which hides the
problem (we measured only ~2.6× degradation that way). Real users keep arriving. The generator
therefore sends a fixed request rate and measures latency from each request's *scheduled* time, so
queueing delay counts. It shares one `httpx.Client` across threads (creating clients is slow on
Windows) and targets `127.0.0.1` (Windows `localhost` → IPv6 first → ~2 s stall per connection).

## Planned layout (created phase by phase)

```
backend/        OpsMind orchestrator: FastAPI + LangGraph + tools + Hindsight memory service
frontend/       React dashboard (Phase 15)
runbooks/       pre-approved runbook definitions (Phase 7)
monitoring/     prometheus/, grafana/ (Phase 3)
infrastructure/ ansible/, jenkins/, terraform/ (Phases 10–11, Terraform later)
```
