# OpsMind — Tech Stack, Architecture & Commands

This is the technical companion to the [project README](README.md). It explains **what** each
technology is, **why** it was chosen, **how** the pieces fit together, and gives **every command**
needed to run, test and troubleshoot the system.

Legend: ✅ built and verified · ⏭ next phase · 🗓 planned

---

## Contents

1. [Tech stack](#1-tech-stack)
2. [Target architecture](#2-target-architecture)
3. [Current architecture (Phases 0–2)](#3-current-architecture-phases-02)
4. [Component internals](#4-component-internals)
5. [Planned components](#5-planned-components)
6. [Configuration & ports](#6-configuration--ports)
7. [Commands](#7-commands)
8. [Troubleshooting](#8-troubleshooting)
9. [Engineering conventions](#9-engineering-conventions)

---

## 1. Tech stack

### 1.1 Overview

| Layer | Technology | Version | Purpose in OpsMind | Status |
|---|---|---|---|---|
| Language | Python | 3.11 | Backend, app, simulator, tools | ✅ |
| Web framework | FastAPI | 0.115.6 | product-api today; OpsMind backend later | ✅ |
| ASGI server | Uvicorn | 0.34.0 | Runs FastAPI apps | ✅ |
| Cache | Redis | 7.4 (alpine) | product-api cache; the incident's battleground | ✅ |
| Database | PostgreSQL | 16 (alpine) | product data | ✅ |
| DB driver | psycopg + psycopg-pool | 3.2.3 / 3.2.4 | parameterized queries, connection pool | ✅ |
| Redis client | redis-py | 5.2.1 | cache + simulator | ✅ |
| Metrics | prometheus-client | 0.21.1 | exposes `/metrics` | ✅ |
| Logs | stdlib `logging` + JSON formatter | — | structured, machine-readable logs | ✅ |
| HTTP client | httpx | 0.28.1 | load generator, tests | ✅ |
| Testing | pytest, pytest-cov, fakeredis | 8.3.4 / 6.0.0 / 2.26.2 | unit + integration tests, coverage gate | ✅ |
| Containers | Docker + Docker Compose | Docker 29 | whole local environment | ✅ |
| Monitoring | Prometheus | — | scrape metrics, alert on latency | ⏭ Phase 3 |
| Dashboards | Grafana | — | latency / errors / cache / traffic | ⏭ Phase 3 |
| Agent orchestration | LangGraph | — | incident workflow graph with typed state | 🗓 Phase 4 |
| LLM (primary) | Gemini Flash (free tier) | — | interpret evidence, diagnose, explain | 🗓 Phase 4 |
| LLM (fallback) | Groq (free tier) | — | fast backup on rate limits / outages | 🗓 Phase 4 |
| Memory | **Hindsight** (self-hosted, Docker) | — | retain / recall operational experience | 🗓 Phase 6 |
| Chat-ops | Slack | — | incident notification + approval | 🗓 Phase 9 |
| Automation | Ansible | — | execute approved runbooks (check mode first) | 🗓 Phase 10 |
| CI/CD | GitHub + Jenkins | — | build, test, deploy, rollback | 🗓 Phase 11 |
| Frontend | React + TypeScript | — | incident dashboard | 🗓 Phase 15 |
| IaC | Terraform | — | infra-change demos only; **not** an MVP dependency | 🗓 later |
| Log aggregation | Loki | — | only if it proves useful | 🗓 optional |

### 1.2 Why these choices

| Choice | Reason |
|---|---|
| **Python + FastAPI** | One language for app, agent, tools and simulator; FastAPI gives validation (Pydantic) and OpenAPI docs for free |
| **LangGraph** | Incident response is a *graph with a pause* (wait for human approval). LangGraph models nodes, typed state and interrupts explicitly — no hand-rolled state machine |
| **Hindsight** | Mandatory for the hackathon, and exactly the right primitive: retain experiences, recall relevant ones. We do **not** build a custom vector DB or duplicate its memory logic |
| **Gemini + Groq, minimal calls** | Free tiers have rate limits. Deterministic code does thresholds, math, validation, risk checks, runbook lookup, execution and verification; the LLM only interprets and explains |
| **Redis + PostgreSQL** | The most common real-world cache + DB pair; cache saturation is a real, recognisable incident |
| **Prometheus + Grafana** | Industry-standard, free, local; PromQL gives P95 latency directly from the histogram |
| **Ansible** | Declarative, idempotent, supports `--check` (dry-run); the LLM never touches a shell |
| **Jenkins** | Free, self-hosted CI/CD; lets us correlate "deploy 7 minutes before the alert" |
| **Slack** | Where on-call engineers already are; approval happens without context-switching |
| **Docker Compose (no Kubernetes)** | A modular monolith on one laptop is enough for the MVP and costs ₹0 |

### 1.3 Deliberately **not** used

Kubernetes · Kafka · separate vector databases · custom ML models · reinforcement-learning frameworks ·
multiple agent frameworks · paid cloud services. They add cost and complexity without improving the demo.

---

## 2. Target architecture

```mermaid
flowchart TD
    Dev[Developer] -->|push| GH[GitHub]
    GH --> JK[Jenkins<br/>build · test · deploy · rollback]
    JK --> APP[product-api<br/>+ Redis + PostgreSQL]
    APP -->|/metrics| PROM[Prometheus]
    APP -->|JSON logs| LOGS[Structured logs]
    PROM --> GRAF[Grafana]
    PROM -->|high-latency alert| ORCH

    subgraph ORCH[OpsMind orchestrator · FastAPI + LangGraph]
        direction TB
        N1[1 · Intake] --> N2[2 · Evidence collection]
        N2 --> N3[3 · Memory recall]
        N3 --> N4[4 · Diagnosis]
        N4 --> N5[5 · Runbook planner]
        N5 --> N6[6 · Human approval ⏸]
        N6 --> N7[7 · Execution]
        N7 --> N8[8 · Verification]
        N8 --> N9[9 · Learning]
    end

    N2 -.tools.-> PROM
    N2 -.tools.-> LOGS
    N2 -.tools.-> JK
    N3 <-->|recall| HS[(Hindsight)]
    N9 -->|retain| HS
    N4 -.structured output.-> LLM[Gemini / Groq]
    N6 <-->|Approve · Edit · Reject · Manual| SL[Slack]
    N7 -->|runbook ID only| ANS[Ansible / Jenkins]
    ANS --> APP
    N8 -.metrics.-> PROM
    ORCH --> UI[React dashboard]
```

### 2.1 Safety pipeline

```
LLM proposes runbook ID ─► policy / risk gate ─► human approval ─► load vetted runbook
       (never shell)          (deterministic)        (Slack)        ─► Ansible (check → run)
                                                                     ─► verify with real metrics
```

### 2.2 Where the LLM is (and isn't) used

| Deterministic code | LLM (structured JSON output) |
|---|---|
| metric math, thresholds, before/after comparison | interpreting combined evidence |
| input / output validation | ranking likely root causes + confidence |
| risk and policy checks | selecting among **valid** runbook IDs |
| runbook lookup and execution | human-readable recommendation and postmortem |
| verification of recovery | incident summaries |

---

## 3. Current architecture (Phases 0–2)

```mermaid
flowchart LR
    subgraph HOST[Windows host]
        SIM[create_incident.py]
        LOAD[load_generator.py<br/>50 req/s fixed rate]
        CURL[curl / browser]
    end

    subgraph COMPOSE[docker compose · project 'opsmind']
        API[product-api<br/>FastAPI · :8000]
        R[(Redis 7.4<br/>32 MB · volatile-lru)]
        PG[(PostgreSQL 16<br/>500 products)]
    end

    LOAD -->|127.0.0.1:8001| API
    CURL -->|127.0.0.1:8001| API
    SIM -->|127.0.0.1:6380<br/>inject / restore sessions| R
    API -->|cache-aside| R
    API -->|on miss · 250 ms query| PG
```

| Container | Image | Host port → container | Health check |
|---|---|---|---|
| `product-api` | built from `product-api/Dockerfile` | `127.0.0.1:8001 → 8000` | `GET /health` |
| `redis` | `redis:7.4-alpine` | `127.0.0.1:6380 → 6379` | `redis-cli ping` |
| `postgres` | `postgres:16-alpine` | `127.0.0.1:5433 → 5432` | `pg_isready` |

Ports are bound to `127.0.0.1` only (not reachable from your network).

---

## 4. Component internals

### 4.1 product-api

A small shop API that is **intentionally instrumented** so OpsMind has real evidence to investigate.

**Endpoints**

| Method & path | Behaviour | Response |
|---|---|---|
| `GET /health` | Pings Redis and PostgreSQL | `200 {"status":"ok"}` or `503 {"status":"degraded"}` |
| `GET /products?limit=N` | Product list (1 ≤ N ≤ 100), cached | `{data, meta:{count, cache}, error}` |
| `GET /products/{id}` | One product (1 ≤ id ≤ 1,000,000), cached | `{data, meta:{cache}, error}`; `404` if unknown |
| `GET /metrics` | Prometheus text format; refreshes Redis gauges | `text/plain` |

All JSON responses use the envelope `{ "data": …, "meta": {…}, "error": … }`.
Every product response carries an `X-Cache: HIT | MISS` header.

**Request path (cache-aside)**

```
GET /products/42
  └─► Redis GET product:42
        ├─ HIT  → return (≈3 ms)                                   cache_hits_total++
        └─ MISS → PostgreSQL: pg_sleep(0.25) + SELECT … WHERE id=%s   cache_misses_total++
                  → Redis SET product:42 (TTL 300 s)  — may be rejected with OOM when saturated
                  → return (≈260 ms)
```

`pg_sleep` stands in for an expensive join/aggregation, so that cache health has a real, causal
effect on latency (not a fake sleep in the handler).

**Modules** (`product-api/app/`)

| File | Responsibility |
|---|---|
| `config.py` | All settings from environment variables with named defaults |
| `cache.py` | Redis JSON get/set, ping, memory stats; Redis failures degrade to misses |
| `db.py` | Schema, deterministic seed, parameterized queries, simulated query cost |
| `service.py` | Cache-aside logic, hit/miss counters |
| `metrics.py` | Metric definitions; refresh Redis gauges; cache-pressure warning |
| `middleware.py` | Per-request metrics + structured request log |
| `logging_setup.py` | JSON log formatter |
| `dependencies.py` | Wires real Redis/Postgres clients (tests inject fakes) |
| `main.py` | Routes, validation, error envelope |

**Metrics**

| Metric | Type | Labels | Use |
|---|---|---|---|
| `http_requests_total` | counter | method, path, status | request rate |
| `http_request_errors_total` | counter | method, path | 5xx rate |
| `http_request_duration_seconds` | histogram | method, path | P50/P95/P99 latency |
| `cache_hits_total`, `cache_misses_total` | counter | — | hit ratio |
| `redis_memory_used_bytes`, `redis_memory_max_bytes` | gauge | — | cache size |
| `redis_memory_utilization_ratio` | gauge | — | used / max (0–1) |
| `redis_evicted_keys` | gauge | — | evictions since Redis start |
| `redis_up` | gauge | — | Redis reachable |

`path` is the **route template** (`/products/{product_id}`), never the raw URL, to keep label
cardinality bounded. Histogram buckets: 5 ms … 10 s.

Useful PromQL (Phase 3):

```promql
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{path="/products/{product_id}"}[1m])))
rate(cache_hits_total[1m]) / (rate(cache_hits_total[1m]) + rate(cache_misses_total[1m]))
sum(rate(http_request_errors_total[1m])) / sum(rate(http_requests_total[1m]))
redis_memory_utilization_ratio
```

**Log events** (one JSON object per line on stdout)

| `event` | Level | When |
|---|---|---|
| `startup` | INFO | app started |
| `db_seed` | INFO | products inserted on first start |
| `http_request` | INFO / WARNING | every request (`/health`, `/metrics` only if slow or failing); WARNING if ≥ 500 ms or 5xx |
| `cache_write_rejected` | WARNING | Redis refused a SET (e.g. OOM) |
| `cache_error` | ERROR | Redis read failed |
| `cache_pressure` | WARNING | Redis utilization ≥ 90% at a metrics scrape |

Example:

```json
{"ts":"2026-09-27T10:27:15.338788+00:00","level":"WARNING","service":"product-api","logger":"product_api.cache","msg":"cache write rejected","event":"cache_write_rejected","key":"product:67","error":"command not allowed when used memory > 'maxmemory'."}
```

### 4.2 Incident simulator

**Scenario `cache` — cache saturation**

```
auth-service deploy drops session TTL (story)
        │
        ▼
~19,000 TTL-less session:* hashes (≈1 KB each) fill Redis to 100%
   ├─ 300 ACTIVE  (last_seen < 30 min)  ← a full flush would log these users out
   └─ rest STALE  (last_seen ≈ 3 days)  ← safe to delete (future RB-CACHE-001)
        │  volatile-lru may only evict keys that have a TTL → the product cache
        ▼
product:* evicted / SET rejected (OOM) → hit ratio 100% → ~5%
        │  each miss = 250 ms, DB pool = 10 connections → capacity ≈ 40 req/s
        ▼
arrivals 50 req/s > capacity → queue grows → P95 13 ms → ~7 s
```

- **Deterministic:** key names are hashes of `(kind, index)`; counts and sizes are constants. The stale
  count varies by a few dozen between runs (Redis memory overhead); the effect does not.
- **Opaque keys:** stale and active sessions are indistinguishable by name — a correct cleanup must
  inspect `last_seen`, just like in real life.
- **`--restore` ≠ runbook:** `--restore` resets the test environment by deleting *all* injected
  sessions. The production runbook will delete only stale ones.

**Load generator — open loop, fixed rate**

| Design point | Why |
|---|---|
| Fixed arrival rate (default 50 req/s) | Real users don't slow down when you do; a closed loop hid the incident (only ~2.6× worse) |
| Latency measured from *scheduled* send time | Queueing delay counts (avoids "coordinated omission") |
| Seeded product-id sequence (`--seed 42`) | Identical traffic every run |
| One shared `httpx.Client` | Creating clients is slow on Windows (TLS bundle load) |
| `127.0.0.1`, not `localhost` | Windows tries IPv6 first; Docker listens on IPv4 only → ~2 s stall per connection |
| Warm-up pass (skippable) | Healthy runs start with a full cache |

### 4.3 Measured results

| | Healthy | During incident | After `--restore` |
|---|---|---|---|
| P50 / P95 / P99 | 10 / 13 / 16 ms | 3.7 / 6.9 / 7.1 s | 9 / 20 / 30 ms |
| Cache hit ratio | 100% | 4.5% | 100% |
| Redis memory | ~4% | 100% | ~4% |
| Errors | 0% | 0% | 0% |

(50 req/s for 30 s, Windows 11 + Docker Desktop. Numbers vary by machine; the shape does not.)

---

## 5. Planned components

### 5.1 LangGraph workflow state (Phase 4)

```python
class IncidentState(TypedDict):
    incident_id: str
    service: str
    severity: str
    symptoms: list[str]
    logs: list[dict]
    metrics: dict
    recent_changes: list[dict]
    historical_memories: list[dict]   # from Hindsight recall
    diagnosis: str
    confidence: float
    evidence: list[str]
    recommended_runbook: str          # a runbook ID, never a command
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    human_decision: Literal["PENDING_APPROVAL", "APPROVED", "MODIFIED", "REJECTED", "EXECUTE_MANUALLY"]
    execution_result: dict
    verification_result: dict
    learning_summary: str
```

### 5.2 Controlled tools (Phase 5)

`get_logs()` · `get_metrics()` · `get_service_health()` · `get_recent_deployments()` · `get_git_changes()`
→ later `select_runbook()` · `execute_runbook()` · `verify_incident()`.
Each tool has an input schema, an output schema, error handling and logging. The AI calls tools rather
than inventing facts.

### 5.3 Memory service (Phase 6)

A thin abstraction over self-hosted Hindsight — no custom vector store:

```python
memory.retain(experience)   # incident, evidence, diagnosis, recommendation, human decision,
                            # modification, execution, verification, lesson
memory.recall(query)        # similar incidents, past remediations (succeeded + failed),
                            # operator preferences, previous runbook modifications
```

If Hindsight is unavailable, the workflow continues without history and says so in the trace.

### 5.4 Runbooks (Phase 7)

| ID | Action | Executor | Risk |
|---|---|---|---|
| `RB-CACHE-001` | Delete sessions whose `last_seen` is older than 24 h | Ansible | Low |
| `RB-SERVICE-001` | Restart product-api | Ansible | Medium |
| `RB-DEPLOY-001` | Roll back to previous build | Jenkins | Medium |

### 5.5 Approval states (Phase 8)

`PENDING_APPROVAL → APPROVED | MODIFIED | REJECTED | EXECUTE_MANUALLY`.
For `MODIFIED`, the original recommendation, the modification and the final action are all recorded
and later retained in Hindsight.

---

## 6. Configuration & ports

All configuration lives in `.env` (git-ignored), created from `.env.example`.

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `POSTGRES_USER` | `opsmind` | compose | DB user |
| `POSTGRES_PASSWORD` | `changeme-local-only` | compose | DB password (letters/digits only — it goes in a URL) |
| `POSTGRES_DB` | `shop` | compose | DB name |
| `PRODUCT_API_PORT` | `8001` | compose | host port for product-api |
| `POSTGRES_HOST_PORT` | `5433` | compose | host port for PostgreSQL |
| `REDIS_HOST_PORT` | `6380` | compose | host port for Redis |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | empty | 🗓 Phase 4 | LLM keys |
| `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_CHANNEL_ID` | empty | 🗓 Phase 9 | Slack app |

product-api tuning (set in `docker-compose.yml` → `environment:` if needed):

| Variable | Default | Meaning |
|---|---|---|
| `CACHE_TTL_SECONDS` | 300 | product cache TTL |
| `SLOW_QUERY_MS` | 250 | simulated cost of a cache miss |
| `SLOW_REQUEST_MS` | 500 | requests slower than this log a WARNING |
| `MEMORY_WARN_RATIO` | 0.90 | Redis utilization that logs `cache_pressure` |
| `SEED_PRODUCT_COUNT` | 500 | products seeded on first start |
| `LOG_LEVEL` | INFO | log level |

Default host ports avoid the common 8000/5432/6379, which are often already in use.

---

## 7. Commands

All commands are **PowerShell**, run from the project root (`...\Hyd3.0\OpsMind`) unless stated.
Use `curl.exe` (in PowerShell, plain `curl` is an alias for `Invoke-WebRequest`).

### 7.1 Prerequisites

```powershell
docker --version          # Docker Desktop with WSL2 backend, running
python --version          # 3.11.x
git --version
```

### 7.2 Start the stack

```powershell
Copy-Item .env.example .env          # first time only — creates your private config
docker compose up -d --build         # build product-api image, start all 3 containers
docker compose ps                    # expect all three "Up ... (healthy)" (~15 s)
```

### 7.3 Verify product-api

```powershell
curl.exe http://127.0.0.1:8001/health
# {"data":{"status":"ok","components":{"redis":"up","postgres":"up"}},"meta":{},"error":null}

curl.exe -i http://127.0.0.1:8001/products/42      # x-cache: MISS  (~260 ms)
curl.exe -i http://127.0.0.1:8001/products/42      # x-cache: HIT   (~3 ms)
curl.exe "http://127.0.0.1:8001/products?limit=3"
curl.exe http://127.0.0.1:8001/products/0          # 422 validation error in the envelope

curl.exe -s http://127.0.0.1:8001/metrics | Select-String "^(cache_|redis_|http_requests_total)"
docker compose logs product-api --tail 20           # JSON log lines
docker compose logs -f product-api                  # follow live (Ctrl+C to stop)
```

Interactive API docs (FastAPI): open <http://127.0.0.1:8001/docs> in a browser.

### 7.4 Incident simulator

One-time setup:

```powershell
cd incident-simulator
python -m venv .venv                                            # isolated Python environment
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Everyday use (inside `incident-simulator\`):

```powershell
.\.venv\Scripts\python.exe create_incident.py --type cache --status    # inspect (read-only)
.\.venv\Scripts\python.exe create_incident.py --type cache             # inject saturation
.\.venv\Scripts\python.exe create_incident.py --type cache --restore   # undo
```

Expected `--status` while the incident is active:

```
  redis memory : 32.0 MB / 32.0 MB  (100.0%)
  evicted keys : 1000
  policy       : volatile-lru
  sessions     : 300 active, 19244 stale
```

Options: `--redis-url redis://127.0.0.1:6380/0` (or env `SIMULATOR_REDIS_URL`).

### 7.5 Load generator

```powershell
.\.venv\Scripts\python.exe load_generator.py                          # 50 req/s for 30 s
.\.venv\Scripts\python.exe load_generator.py --duration 20            # shorter
.\.venv\Scripts\python.exe load_generator.py --rate 80 --duration 60  # heavier
.\.venv\Scripts\python.exe load_generator.py --no-warmup              # use during an incident
```

| Option | Default | Meaning |
|---|---|---|
| `--rate` | 50 | requests per second (fixed, open-loop) |
| `--duration` | 30 | seconds |
| `--seed` | 42 | product-id sequence seed |
| `--api-url` | `http://127.0.0.1:8001` | target |
| `--no-warmup` | off | skip the "touch every product once" pass |

Sample output:

```
Sending 50 req/s for 30s...
  requests  : 1500 completed (39.8 req/s incl. drain)
  errors    : 0.0%
  latency   : p50 3724 ms | p95 6924 ms | p99 7144 ms
  cache hit : 4.5%
```

### 7.6 Full demo cycle

```powershell
cd incident-simulator
$py = ".\.venv\Scripts\python.exe"
& $py load_generator.py --duration 20                   # 1. healthy baseline
& $py create_incident.py --type cache                   # 2. inject
& $py load_generator.py --duration 20 --no-warmup       # 3. observe incident
docker compose logs product-api --tail 5                #    evidence in logs
& $py create_incident.py --type cache --restore         # 4. reset
& $py load_generator.py --duration 20                   # 5. recovered
```

### 7.7 Tests

product-api (unit tests need nothing running; integration tests need the stack):

```powershell
cd product-api
python -m venv .venv                                              # first time only
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt # first time only
.\.venv\Scripts\python.exe -m pytest                              # unit tests (integration skipped)

$env:TEST_DATABASE_URL = "postgresql://opsmind:changeme-local-only@127.0.0.1:5433/shop"
$env:TEST_REDIS_URL    = "redis://127.0.0.1:6380/15"             # DB 15: isolated from the app
.\.venv\Scripts\python.exe -m pytest                              # all 24 tests
```

incident-simulator:

```powershell
cd incident-simulator
.\.venv\Scripts\python.exe -m pytest                              # 31 tests, no containers needed
```

Both suites enforce **≥ 80% coverage** (line + branch) and fail below it.

### 7.8 Stop, restart, reset

```powershell
docker compose stop                              # pause containers (keeps everything)
docker compose start                             # resume
docker compose restart product-api               # restart one service
docker compose up -d --build product-api         # rebuild after changing app code
docker compose up -d --force-recreate redis      # recreate Redis (e.g. after config change; empties it)
docker compose down                              # remove containers, keep DB data
docker compose down -v                           # remove containers AND DB data (re-seeded next start)
```

### 7.9 Poking at the internals

```powershell
docker compose exec redis redis-cli INFO memory | Select-String "used_memory_human|maxmemory_human|maxmemory_policy"
docker compose exec redis redis-cli DBSIZE
docker compose exec redis redis-cli --scan --pattern "product:*" | Select-Object -First 5
docker compose exec postgres psql -U opsmind -d shop -c "SELECT COUNT(*) FROM products;"
docker stats --no-stream                         # CPU / memory per container
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` | Another program uses that host port | Change `PRODUCT_API_PORT` / `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` in `.env`, then `docker compose up -d` |
| `set POSTGRES_USER in .env` | `.env` missing | `Copy-Item .env.example .env` |
| product-api `unhealthy` or restarting | Usually DB credentials changed after the volume was created | `docker compose logs product-api`; if auth error: `docker compose down -v` then `up -d` |
| `/health` → `postgres: down` | Postgres still starting | `docker compose ps postgres`; wait for `healthy` |
| `Cannot reach Redis at …` (simulator) | Stack not running or port changed | `docker compose ps`; pass `--redis-url` |
| `--status` shows `allkeys-lru` | Redis container predates Phase 2 | `docker compose up -d --force-recreate redis` |
| Incident injected but latency normal | Redis not full or wrong policy | `--status` must show ~100% and `volatile-lru` |
| p99 ≈ 2000 ms even when healthy | Using `localhost` on Windows (IPv6 stall) | Use `127.0.0.1` |
| `curl` prompts or prints odd objects | PowerShell alias | Use `curl.exe` |
| Integration tests `Connection refused` | Stack down or wrong `TEST_*` URLs | Start stack; match ports in `.env` |
| `docker` commands hang / fail | Docker Desktop not running | Start Docker Desktop, wait for "Engine running" |

---

## 9. Engineering conventions

- **Security:** no secrets in source (`.env` is git-ignored); parameterized SQL only; inputs validated
  at the API boundary; containers run as non-root; ports bound to `127.0.0.1`.
- **Code:** functions ≤ 40 lines, files ≤ 300 lines, named constants instead of magic numbers,
  boolean names prefixed `is_/has_/can_/should_`.
- **API:** plural resources, `{data, meta, error}` envelope, bounded metric labels.
- **Tests:** behaviour over implementation; ≥ 80% line / 75% branch coverage; integration tests are
  skipped (with a documented reason) when the stack isn't running.
- **Git:** conventional commits (`type(scope): subject`), branch prefixes `feature/ fix/ refactor/ docs/`,
  one logical change per PR.
- **Docs:** README, TECH_STACK, CHANGELOG and `docs/` are updated in every phase.
