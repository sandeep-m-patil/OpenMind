# OpsMind — Tech Stack, Architecture & Commands

Technical companion to the [project README](README.md): **what** each technology is, **why** it was
chosen, **how** the pieces fit, and **every command** to run, test and troubleshoot the system.

---

## Contents

1. [Tech stack](#1-tech-stack)
2. [Architecture](#2-architecture)
3. [Containers & ports](#3-containers--ports)
4. [Component internals](#4-component-internals)
5. [Configuration](#5-configuration)
6. [Measured results](#6-measured-results)
7. [Commands](#7-commands)
8. [Troubleshooting](#8-troubleshooting)
9. [Engineering conventions](#9-engineering-conventions)

---

## 1. Tech stack

### 1.1 Overview

| Layer | Technology | Version | Role in OpsMind |
|---|---|---|---|
| Language | Python | 3.11 | backend, product-api, simulator, runbook scripts |
| API framework | FastAPI + Uvicorn | 0.141 / 0.54 (backend), 0.115 / 0.34 (product-api) | REST APIs |
| Agent orchestration | **LangGraph** | 1.2.12 | 9-node incident workflow, typed state, human interrupt |
| Workflow persistence | langgraph-checkpoint-postgres | 3.1.2 | the paused graph survives restarts |
| Memory | **Hindsight** (self-hosted, [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight)) | API 0.10.1 | retain / recall operational experience |
| LLM (primary) | Google Gemini (REST, JSON mode) | `gemini-2.5-flash` (configurable) | diagnosis + runbook choice, 1 call per incident |
| LLM (fallback) | Groq (OpenAI-compatible REST, JSON mode) | `llama-3.3-70b-versatile` (configurable) | used on Gemini failure / rate limit |
| LLM (last resort) | Deterministic rule engine | — | works with no key at all |
| Cache | Redis | 7.4-alpine | product cache; the incident's battleground |
| Database | PostgreSQL | 16-alpine | products (`shop`), OpsMind records + checkpoints (`opsmind`) |
| Metrics | prometheus-client → Prometheus | 0.21.1 → v2.53.0 | request/latency/cache/Redis metrics, alert rules |
| Alerting | Alertmanager | v0.27.0 | webhook → OpsMind |
| Dashboards | Grafana | 11.1.0 | provisioned product-api dashboard |
| Logs | JSON lines (stdout + shared file) | — | read by the `get_logs` tool |
| Automation | **Ansible** (ansible-core) | 2.19.13 | executes approved runbooks, `--check` first |
| CI/CD | Jenkins LTS (JDK 21) + config-as-code + job-dsl | lts | build / test / deploy `build-N`, rollback |
| Chat-ops | Slack (slack-sdk, Socket Mode) | 3.44.1 | incident message + Approve / Reject / Manual buttons |
| Frontend | React + TypeScript + Vite + React Router | 19.3 / 7.0 / 8.3 / 7.18 | dashboard, served by nginx 1.29 |
| Testing | pytest, pytest-cov, fakeredis, Vitest, Testing Library | — | ≥ 80 % coverage gates everywhere |
| Containers | Docker Desktop + Compose | Docker 29 | the whole environment |

### 1.2 Why these choices

| Choice | Reason |
|---|---|
| **LangGraph** | Incident response is a *graph with a pause*: it must stop for a human, possibly for hours, then resume. LangGraph's `interrupt()` + Postgres checkpointer gives exactly that, with typed state and conditional routing |
| **Hindsight, self-hosted** | Mandatory for the hackathon and the right primitive: retain experiences, recall relevant ones. Runs locally with embedded Postgres and local embeddings; `HINDSIGHT_API_LLM_PROVIDER=none` needs **no API key**. We don't build a vector store or re-rank on top |
| **One LLM call per incident** | Free tiers are rate-limited. Code does thresholds, arithmetic, validation, risk, lookup, execution and verification; the LLM only interprets evidence and chooses among valid runbooks |
| **REST instead of LLM SDKs** | Two small `httpx` calls instead of two heavy SDKs; keys go in headers, never URLs |
| **Ansible** | Declarative, idempotent, real `--check` mode; the AI never touches a shell |
| **Jenkins with config-as-code** | Free, self-hosted; jobs are defined in files, so `docker compose up` gives a ready Jenkins with no clicking |
| **Slack Socket Mode** | Button clicks arrive over an outbound websocket — works on a laptop with no public URL or ngrok |
| **Docker Compose, no Kubernetes** | A modular monolith on one laptop is enough for the MVP and costs ₹0 |

### 1.3 Deliberately **not** used

Kubernetes · Kafka · separate vector databases · custom ML models · reinforcement-learning frameworks ·
multiple agent frameworks · paid cloud services · Terraform (out of MVP scope).

---

## 2. Architecture

### 2.1 System

```mermaid
flowchart TD
    Dev[Developer] -->|Build Now / git| JK[Jenkins<br/>test · build build-N · deploy · smoke test]
    JK -->|deploy| APP[product-api<br/>+ Redis + PostgreSQL]
    JK -->|POST /v1/deployments| ORCH
    APP -->|/metrics every 5 s| PROM[Prometheus]
    APP -->|JSON log file| LOGS[(shared log volume)]
    PROM --> GRAF[Grafana]
    PROM -->|HighLatency firing| AM[Alertmanager]
    AM -->|webhook| ORCH

    subgraph ORCH[OpsMind backend · FastAPI + LangGraph]
        direction TB
        N1[1 Intake] --> N2[2 Evidence]
        N2 --> N3[3 Recall]
        N3 --> N4[4 Diagnosis]
        N4 --> N5[5 Planner + policy]
        N5 --> N6[6 Approval ⏸]
        N6 -->|approved / modified| N7[7 Execution]
        N6 -->|execute manually| N8
        N6 -->|rejected| N9
        N7 -->|ok| N8[8 Verification]
        N7 -->|dry run failed| N9
        N8 --> N9[9 Learning]
    end

    N2 -.tools.-> PROM
    N2 -.tools.-> LOGS
    N3 <-->|recall| HS[(Hindsight)]
    N9 -->|retain| HS
    N4 -.JSON.-> LLM[Gemini → Groq → rules]
    N6 <-->|buttons| SL[Slack]
    N6 <-->|decisions| UI[React dashboard]
    N7 -->|runbook ID → playbook| ANS[Ansible]
    ANS -->|Redis / Docker API / Jenkins| APP
    N8 -.real metrics.-> PROM
    ORCH --- DB[(PostgreSQL · opsmind<br/>incidents · deployments · scores · checkpoints)]
```

### 2.2 Safety pipeline

```
LLM proposes a runbook ID ──► code validates ID + params ──► policy gate (risk, overruled?) ──► ⏸ human
      (never a command)          (catalog, types, bounds)                                        │
                                                                                                 ▼
        verify from Prometheus ◄── ansible-playbook apply ◄── ansible-playbook --check (dry run) ◄┘
```

### 2.3 Where the LLM is and isn't used

| Deterministic code | LLM (one structured-JSON call) |
|---|---|
| metric queries, baselines, ratios, thresholds → findings | interpret the combined evidence |
| log aggregation | root cause, category, confidence |
| memory → preferred / overruled runbooks | choose among **catalog** runbooks, citing history |
| parameter validation, risk & policy | human-readable rationale |
| execution, verification, lesson text, strategy scores | — |

Without any key, the **rule engine** replaces the LLM column. It encodes a textbook first response
(cache saturation → flush) and lets memory override it — which is why the learning loop works at ₹0.

---

## 3. Containers & ports

All ports are bound to `127.0.0.1` (not reachable from your network).

| Service | Image | Host port | Purpose |
|---|---|---|---|
| `product-api` | `opsmind-product-api:${PRODUCT_API_TAG:-latest}` | 8001 | watched application |
| `redis` | redis:7.4-alpine | 6380 | 32 MB cache, `volatile-lru` |
| `postgres` | postgres:16-alpine | 5433 | `shop` + `opsmind` databases |
| `prometheus` | prom/prometheus:v2.53.0 | 9090 | metrics + alert rules |
| `alertmanager` | prom/alertmanager:v0.27.0 | 9093 | alert → OpsMind webhook |
| `grafana` | grafana/grafana:11.1.0 | 3001 | dashboard (anonymous viewer) |
| `hindsight` | ghcr.io/vectorize-io/hindsight:latest | 8888 (API), 9999 (UI) | memory |
| `opsmind-backend` | built from `backend/` | 8002 | orchestrator API (`/docs` for OpenAPI) |
| `dashboard` | built from `frontend/` | 3002 | React UI + `/v1` proxy |
| `jenkins` *(profile `cicd`)* | built from `infrastructure/jenkins/` | 8081 | CI/CD |

Volumes: `postgres-data`, `hindsight-data`, `product-api-logs` (shared read-only with the backend), `jenkins-home`.

---

## 4. Component internals

### 4.1 Backend layout (`backend/app/`)

| Path | Responsibility |
|---|---|
| `agents/graph.py` | builds the StateGraph; wraps every node to persist its output (live dashboard) |
| `agents/state.py` | `IncidentState` TypedDict; append-only `trace` via reducer |
| `agents/nodes/*.py` | one file per node (intake … learning) |
| `agents/analysis.py` | signals + human-readable findings + recall query (no LLM) |
| `agents/memory_guidance.py` | recalled memories → preferred / overruled runbooks, operator comments |
| `agents/rules.py` | deterministic diagnosis + runbook choice (memory-aware) |
| `agents/prompts.py` | the single diagnosis prompt |
| `agents/verdict.py` | did metrics recover? (pure function) |
| `agents/learning_record.py` | narrative + metadata + lesson retained in Hindsight |
| `tools/` | `get_metrics` (Prometheus), `get_logs` (log file), `get_service_health`; uniform `ToolResult` |
| `services/memory.py` | Hindsight HTTP client (`retain`, `recall`) |
| `services/llm.py` | Gemini → Groq chain, JSON validation, corrective retry |
| `services/runbooks.py`, `policy.py`, `decisions.py` | catalog, parameter validation, risk gate, human decision → final action |
| `services/executor.py` | `ansible-playbook` runner (argv list, no shell, timeout, dry run) |
| `services/workflow.py` | background runner: open incident, resume with decision, dedupe, error capture |
| `services/slack*.py` | Block Kit messages, notifier, Socket Mode listener |
| `services/*_store.py`, `strategy_scores.py` | PostgreSQL records (parameterized SQL only) |
| `api/` | REST routes |

### 4.2 Workflow state (abridged)

```python
class IncidentState(TypedDict, total=False):
    incident_id: str; service: str; severity: str; title: str; symptoms: list[str]; status: str
    metrics: dict; logs: dict; health: dict; recent_changes: list[dict]; findings: list[str]; signals: dict
    historical_memories: list[dict]; memory_guidance: dict; memory_status: str
    diagnosis: dict; confidence: float; evidence: list[str]; diagnosis_engine: dict
    recommended_runbook: str | None; recommended_params: dict; risk: str | None; policy: dict
    human_decision: dict; final_action: dict; metrics_before: dict
    execution_result: dict; verification_result: dict
    outcome: str; learning_summary: str; memory_retained: bool
    trace: Annotated[list[TraceEntry], operator.add]
```

Status lifecycle: `INVESTIGATING → PENDING_APPROVAL → DECISION_RECORDED → EXECUTING → VERIFYING →
RESOLVED | REMEDIATION_FAILED | VERIFICATION_INCONCLUSIVE | REJECTED | ERROR`
(`AWAITING_MANUAL_EXECUTION` for manual execution).

### 4.3 REST API (`http://127.0.0.1:8002`, envelope `{data, meta, error}`)

| Method & path | Purpose |
|---|---|
| `GET /health` | component status (Prometheus, Hindsight, LLM, Slack) |
| `POST /v1/alerts/prometheus` | Alertmanager webhook; critical firing alerts open incidents (duplicates absorbed) |
| `POST /v1/incidents` | manual trigger |
| `GET /v1/incidents?limit=&before=` | newest first, cursor pagination |
| `GET /v1/incidents/{id}` | full state + trace |
| `POST /v1/incidents/{id}/decisions` | `{decision, operator, comment, runbook_id?, params?}` → 202 · 404 · 409 · 422 |
| `GET /v1/runbooks` · `GET /v1/strategies` | catalog · strategy scores |
| `GET /v1/memories?query=&service=` | Hindsight recall passthrough |
| `POST /v1/deployments` · `GET /v1/deployments` | deployment events (Jenkins, simulator) |

### 4.4 Memory (Hindsight)

- **Retain** — `POST /v1/default/banks/opsmind-sre/memories` with one item per incident:
  narrative (`content`), `document_id` = incident ID, `metadata` (strings), tags
  `service:…`, `category:…`, `outcome:…`.
- **Recall** — `POST …/memories/recall` with a query built from observed symptoms and
  `tags=["service:product-api"]`, `tags_match="any_strict"`.
- Default mode `none` stores memories verbatim and recalls them by semantic + keyword search (local
  embeddings, no key). Set `HINDSIGHT_LLM_PROVIDER=gemini` (+ key + model) for fact extraction.

### 4.5 Verification

After execution, every 10 s for up to 150 s (300 s for manual execution), Prometheus is queried over a
30 s window. **Resolved** requires *all* of: P95 ≤ 0.5 s, P95 at least halved vs before, service
healthy, and (for cache incidents) hit ratio ≥ 80 %. No traffic → `VERIFICATION_INCONCLUSIVE`.

### 4.6 Strategy score

`score = succeeded ÷ (proposed + adopted)`, where *adopted* = times a human switched **to** that runbook.
Spec example: approved 9, modified 1, succeeded 9 → 9 / 10 = **0.90**.

### 4.7 product-api & simulator

- product-api: cache-aside (`X-Cache: HIT|MISS`), a miss costs `SLOW_QUERY_MS` = 250 ms; metrics
  `http_request_duration_seconds`, `cache_hits_total`, `cache_misses_total`,
  `redis_memory_utilization_ratio`, `redis_evicted_keys`, …; log events `http_request`,
  `cache_write_rejected`, `cache_pressure`.
- Simulator: writes TTL-less `session:*` hashes (300 active, ~19k stale) until Redis refuses writes, then
  tops up with single writes so severity is the same every run; records the story's auth-service
  deployment in OpsMind. The load generator is fixed-rate (open-loop) and measures from scheduled send time.

### 4.8 Monitoring

- Alert `HighLatency`: P95 of `GET /products/{id}` over 1 m > 1 s for 30 s → **opens an incident**.
- `CacheSaturation` (Redis > 95 %) and `HighErrorRate` (> 5 %) are warnings / critical; only
  `severity=critical` opens incidents, and an open incident absorbs further alerts.
- Grafana dashboard *OpsMind — product-api*: P95, hit ratio, Redis memory, error rate, request rate,
  evictions.

### 4.9 Jenkins

- `product-api-deploy`: copy source → `pytest` → `docker build -t opsmind-product-api:build-N` →
  `PRODUCT_API_TAG=build-N docker compose up -d --no-deps --no-build product-api` → smoke test
  `/health` → `POST /v1/deployments` (commit, author, recent changes).
- `product-api-rollback`: redeploys the newest `build-K` older than the running one (or the newest CI
  build if the running image is a local build), smoke test, report. Triggered by `RB-DEPLOY-001`.

---

## 5. Configuration

`.env` (git-ignored) is created from `.env.example`; every value has a working default.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | opsmind / changeme-local-only / shop | database |
| `*_PORT` | see §3 | host ports |
| `GRAFANA_ADMIN_PASSWORD` | changeme-local-only | Grafana admin |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | empty, gemini-2.5-flash | optional primary LLM |
| `GROQ_API_KEY`, `GROQ_MODEL` | empty, llama-3.3-70b-versatile | optional fallback LLM |
| `HINDSIGHT_BANK` | opsmind-sre | memory bank |
| `HINDSIGHT_LLM_PROVIDER` / `_API_KEY` / `_MODEL` | none / – / – | Hindsight's own extraction LLM |
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CHANNEL_ID` | empty | optional Slack |
| `JENKINS_ADMIN_USER` / `JENKINS_ADMIN_PASSWORD` | admin / changeme-local-only | Jenkins (also used by `RB-DEPLOY-001`) |

Backend tuning (compose `environment:`): `VERIFY_TIMEOUT_SECONDS` 150, `VERIFY_POLL_SECONDS` 10,
`VERIFY_P95_TARGET_SECONDS` 0.5, `EXECUTION_TIMEOUT_SECONDS` 120, `EVIDENCE_WINDOW_MINUTES` 5,
`DEPLOY_LOOKBACK_MINUTES` 60.

---

## 6. Measured results

Clean run from blank memory, 50 req/s, Windows 11 + Docker Desktop (numbers vary by machine; the shape doesn't):

| | Healthy | INC-1001 | INC-1002 |
|---|---|---|---|
| P95 (Prometheus) | 5 ms | 4.6 s → **313 ms** after RB-CACHE-001 | 4.9 s → **276 ms** after RB-CACHE-001 |
| Cache hit ratio | 100 % | 18 % → 93 % | 8 % → 96 % |
| Redis memory | 4 % | 100 % → 6 % | 100 % → 6 % |
| Recommendation | — | RB-CACHE-002 (HIGH, 80 %) → **modified** | **RB-CACHE-001 (LOW, 92 %)** → approved |
| Alert → pending approval | — | ≈ 60 s (50 s alert `for:` + ~10 s investigation) | same |
| Execution | — | dry run + apply ≈ 4 s | same |

---

## 7. Commands

All commands are **PowerShell**, from the project root unless stated. Use `curl.exe`, not `curl`.

### 7.1 Prerequisites

```powershell
docker --version          # Docker Desktop (WSL2 backend), running
python --version          # 3.11.x
node --version            # 24.x — only for dashboard development
```

### 7.2 Start / stop

```powershell
Copy-Item .env.example .env                    # first time only
docker compose up -d --build                   # everything except Jenkins
docker compose --profile cicd up -d jenkins    # optional: Jenkins (~1 GB RAM)
docker compose ps                              # all Up; product-api/redis/postgres "(healthy)"
curl.exe http://127.0.0.1:8002/health          # prometheus up, hindsight up, llm, slack
docker compose stop                            # pause (keeps data)
docker compose down                            # remove containers (keeps volumes)
docker compose down -v                         # remove containers AND all data (DB, memory, Jenkins)
```

### 7.3 Incident simulator (one-time setup)

```powershell
cd incident-simulator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 7.4 Run the demo

From `incident-simulator\`:

```powershell
.\.venv\Scripts\python.exe reset_demo.py --yes                     # blank slate (irreversible)
.\.venv\Scripts\python.exe load_generator.py --duration 1200       # separate terminal; wait ≥ 2 min
.\.venv\Scripts\python.exe create_incident.py --type cache         # inject (records auth-service deploy)
.\.venv\Scripts\python.exe create_incident.py --type cache --status
.\.venv\Scripts\python.exe create_incident.py --type cache --restore   # test reset (all sessions)
```

| Script option | Meaning |
|---|---|
| `load_generator.py --rate 50 --duration 30 --seed 42 --no-warmup` | fixed-rate traffic |
| `create_incident.py --no-deploy-event` | don't record the story deployment |
| `create_incident.py --opsmind-url / --redis-url` | non-default endpoints |

### 7.5 Drive OpsMind from the command line

```powershell
curl.exe -s "http://127.0.0.1:8002/v1/incidents?limit=5"
curl.exe -s http://127.0.0.1:8002/v1/incidents/INC-1001
curl.exe -s -X POST http://127.0.0.1:8002/v1/incidents/INC-1001/decisions -H "Content-Type: application/json" `
  -d '{\"decision\":\"MODIFIED\",\"operator\":\"you\",\"runbook_id\":\"RB-CACHE-001\",\"comment\":\"Only remove stale session keys\"}'
curl.exe -s -X POST http://127.0.0.1:8002/v1/incidents/INC-1002/decisions -H "Content-Type: application/json" `
  -d '{\"decision\":\"APPROVED\",\"operator\":\"you\"}'
curl.exe -s http://127.0.0.1:8002/v1/strategies
curl.exe -s "http://127.0.0.1:8002/v1/memories?query=cache%20saturation"
curl.exe -s -X POST http://127.0.0.1:8002/v1/incidents -H "Content-Type: application/json" -d '{\"title\":\"Manual check\"}'
```

### 7.6 Tests

```powershell
# backend (126 tests; integration tests need the stack and TEST_DATABASE_URL)
cd backend; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:TEST_DATABASE_URL = "postgresql://opsmind:changeme-local-only@127.0.0.1:5433/opsmind_test"
.\.venv\Scripts\python.exe -m pytest

# product-api (24 tests)
cd ..\product-api; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:TEST_DATABASE_URL = "postgresql://opsmind:changeme-local-only@127.0.0.1:5433/shop"
$env:TEST_REDIS_URL    = "redis://127.0.0.1:6380/15"
.\.venv\Scripts\python.exe -m pytest

# incident-simulator (38 tests, no containers needed)
cd ..\incident-simulator; .\.venv\Scripts\python.exe -m pytest

# dashboard (21 tests + type check + build)
cd ..\frontend; npm ci; npm test; npm run typecheck; npm run build
```

### 7.7 Dashboard development

```powershell
cd frontend
npm ci
npm run dev          # http://127.0.0.1:3002 with hot reload; proxies /v1 to the backend on 8002
```

(Stop the `dashboard` container first — both use port 3002 — or set `DASHBOARD_PORT` in `.env`.)

### 7.8 Jenkins

```powershell
docker compose --profile cicd up -d --build jenkins     # first build ~5 min
```

Open <http://127.0.0.1:8081>, log in with `JENKINS_ADMIN_USER` / `JENKINS_ADMIN_PASSWORD`, run
**product-api-deploy → Build Now**. Each run deploys `opsmind-product-api:build-N` and appears in OpsMind's
deployment evidence. **product-api-rollback** is what `RB-DEPLOY-001` triggers.

> After a Jenkins deploy, restart *other* services with `--no-deps` (e.g.
> `docker compose up -d --no-deps opsmind-backend`); a plain `docker compose up` recreates product-api
> with the default `latest` image.

### 7.9 Enable Gemini / Groq

Get a free key (Gemini: <https://aistudio.google.com/apikey>, Groq: <https://console.groq.com/keys>),
put it in `.env`, then:

```powershell
docker compose up -d --no-deps opsmind-backend
curl.exe -s http://127.0.0.1:8002/health     # "llm": "configured"
```

The incident trace then shows `Engine: gemini/gemini-2.5-flash`; failures fall back to Groq, then rules.

### 7.10 Enable Slack

1. <https://api.slack.com/apps> → **Create New App → From an app manifest** → paste
   `infrastructure/slack/app-manifest.yml`.
2. **Basic Information → App-Level Tokens** → generate with scope `connections:write` → `SLACK_APP_TOKEN` (`xapp-…`).
3. **Install App** → copy the Bot token → `SLACK_BOT_TOKEN` (`xoxb-…`).
4. Invite the bot to a channel (`/invite @OpsMind`), copy the channel ID → `SLACK_CHANNEL_ID`.
5. `docker compose up -d --no-deps opsmind-backend` → `/health` shows `"slack": "enabled"`.

Approve / Reject / Execute-manually work from Slack; **Edit** opens the dashboard. Without an app token,
OpsMind still posts notifications and you approve in the dashboard.

### 7.11 Inspect internals

```powershell
docker compose logs -f opsmind-backend                    # JSON logs (tool calls, runbook runs, memory)
docker compose exec redis redis-cli INFO memory | Select-String "used_memory_human|maxmemory_policy"
docker compose exec postgres psql -U opsmind -d opsmind -c "SELECT id, status FROM incidents ORDER BY created_at;"
curl.exe -s http://127.0.0.1:9090/api/v1/alerts          # Prometheus alert states
curl.exe -s http://127.0.0.1:8888/health                  # Hindsight
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` | host port in use | change the `*_PORT` in `.env`, `docker compose up -d` |
| `set … in .env` | `.env` missing a value | re-copy from `.env.example` |
| No incident after injecting | no traffic, or alert not fired yet | keep `load_generator.py` running; check <http://127.0.0.1:9090/alerts> (≈ 50 s) |
| Evidence says "baseline of 800 ms" | traffic started just before the incident | let traffic run ≥ 2 min first |
| Incident mild, P95 < 1 s | Redis not fully saturated | run `create_incident.py --type cache` again |
| `--status` shows `allkeys-lru` | old Redis container | `docker compose up -d --force-recreate redis` |
| Stuck in *Verifying* | no traffic during verification | keep load running; ends as *inconclusive* after 150 s |
| `/health`: `hindsight: down` | still starting (first start downloads the embedding model) | wait 1–2 min; `docker compose logs hindsight` |
| Trace: "Hindsight unavailable" | Hindsight stopped | `docker compose up -d hindsight`; OpsMind keeps working meanwhile |
| Trace: "LLM unavailable, fell back to rules" | bad key / rate limit / offline | check `.env`; the rule engine keeps the demo working |
| RB-DEPLOY-001 `401 Unauthorized` | backend started before Jenkins creds were set | `docker compose up -d --no-deps opsmind-backend` |
| product-api back on `latest` after a Jenkins deploy | plain `docker compose up` | use `--no-deps` (see §7.8) |
| p99 ≈ 2 s from scripts | `localhost` on Windows (IPv6 first) | use `127.0.0.1` |
| `curl` prompts oddly | PowerShell alias | use `curl.exe` |

---

## 9. Engineering conventions

- **Security:** no secrets in source (`.env` git-ignored); parameterized SQL only (identifiers only from
  allowlists); inputs validated at the boundary with Pydantic; runbook parameters validated against the
  catalog; subprocesses use argv lists (no shell); LLM keys sent in headers; ports bound to 127.0.0.1.
  **Local-demo trade-off:** the backend and Jenkins mount the Docker socket (root-equivalent on the host)
  for `RB-SERVICE-001` and deployments, and the OpsMind API has no authentication — do not expose it.
- **Code:** functions ≤ 40 lines, files ≤ 300 lines, named constants, boolean prefixes `is_/has_`.
- **API:** plural resources, `{data, meta, error}`, cursor pagination, `/v1/` versioning.
- **Tests:** behaviour over implementation, ≥ 80 % line coverage; integration tests skip with a
  documented reason when the stack isn't running.
- **Git:** conventional commits, `feature/ fix/ refactor/ docs/` branches.
