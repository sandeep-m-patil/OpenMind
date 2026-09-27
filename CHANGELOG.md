# Changelog

All notable changes to OpsMind. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added — Phases 3–15 (2026-09-27)
- **Phase 3 — monitoring**: Prometheus (5 s scrape, `HighLatency` / `CacheSaturation` / `HighErrorRate`
  rules), Alertmanager webhook → OpsMind, Grafana with a provisioned product-api dashboard.
- **Phases 4–5 — OpsMind backend** (`backend/`): FastAPI + LangGraph 1.2 workflow with 9 nodes
  (intake, evidence, recall, diagnosis, planner, approval, execution, verification, learning), typed
  state, append-only trace, Postgres checkpointer and a human-approval interrupt. Evidence tools
  `get_metrics`, `get_logs`, `get_service_health`, `get_recent_deployments`, `get_git_changes` with a
  uniform never-raise result contract; deterministic findings (e.g. "P95 2.2 s vs a baseline of 5 ms").
- **Diagnosis**: one structured-JSON LLM call (Gemini → Groq) with validation and corrective retry;
  deterministic, memory-aware rule engine when no key is set or all providers fail.
- **Phase 6 — Hindsight**: self-hosted `ghcr.io/vectorize-io/hindsight` (no-key chunks mode by default);
  `MemoryService.retain` / `recall`; recall runs before diagnosis; memory guidance (preferred / overruled
  runbooks, operator comments).
- **Phase 7 — runbooks**: YAML catalog `RB-CACHE-001` (targeted stale-session cleanup), `RB-CACHE-002`
  (full flush, HIGH), `RB-SERVICE-001` (restart), `RB-DEPLOY-001` (rollback); typed/bounded/allowlisted
  parameters; policy gate that raises the risk of previously overruled runbooks.
- **Phase 8 — approval**: APPROVED / MODIFIED / REJECTED / EXECUTE_MANUALLY; decisions validated before
  resuming (422), race-free claim (409); original recommendation, modification and final action recorded.
- **Phase 9 — Slack**: Block Kit incident message (evidence, confidence, history, runbook, risk) with
  Approve / Edit / Reject / Execute-manually; Socket Mode listener; outcome posted in thread; app manifest.
- **Phase 10 — Ansible**: playbooks + scripts per runbook; every run is `--check` first, then apply;
  structured JSON reports; argv-only execution with timeout.
- **Phase 11 — Jenkins** (compose profile `cicd`): config-as-code, `product-api-deploy` (test → build
  `build-N` → deploy → smoke test → report deployment to OpsMind) and `product-api-rollback`.
- **Phase 12 — verification**: polls Prometheus until P95 ≤ 0.5 s, P95 halved, service healthy and hit
  ratio ≥ 80 %; RESOLVED / REMEDIATION_FAILED / VERIFICATION_INCONCLUSIVE.
- **Phase 13 — learning**: narrative + metadata postmortem retained per incident; measured learning
  loop: INC-1001 recommends RB-CACHE-002 (HIGH, 80 %) → human modifies → INC-1002 recommends
  RB-CACHE-001 (LOW, 92 %) citing INC-1001.
- **Phase 14 — strategy scores**: `succeeded ÷ (proposed + adopted)` per runbook.
- **Phase 15 — dashboard** (`frontend/`): React 19 + TypeScript + Vite, nginx; incidents list,
  incident detail (key facts, live trace, evidence, recalled memory, diagnosis, policy, decision panel,
  execution, before/after verification, lesson), learning page (scores, memory search, catalog).
- `incident-simulator/reset_demo.py --yes`: blank incidents, scores, checkpoints and Hindsight memory.
- Tests: backend 126 (94 %), dashboard 21 (98 % lines), simulator 38 (97 %), product-api 24 (96 %).

### Changed — Phases 3–15
- product-api also writes JSON logs to a shared volume (`LOG_FILE`) for the `get_logs` tool.
- product-api image is tagged `opsmind-product-api:${PRODUCT_API_TAG:-latest}` so Jenkins can deploy
  and roll back versioned builds.
- Simulator: tops up Redis with single writes after the bulk fill hits OOM (freed pipeline buffers made
  the incident's severity vary between runs); records the story's auth-service deployment in OpsMind.
- Simulator and load generator default to `127.0.0.1` (Windows `localhost` resolves to IPv6 first).

### Docs (2026-09-27)
- README, TECH_STACK, docs/architecture.md, docs/setup.md and docs/demo.md rewritten for the complete
  system with measured results.

### Docs (earlier, 2026-09-27)
- Rewrote `README.md` as the detailed project overview (problem, workflow, learning loop, demo story,
  safety model, status, judging-criteria mapping).
- Added `TECH_STACK.md`: stack with versions and rationale, target and current architecture diagrams,
  component internals, configuration, every command, troubleshooting.

### Added — Phase 2 (2026-09-27)
- `incident-simulator/create_incident.py --type cache [--status|--restore]`: deterministic cache
  saturation — fills Redis with TTL-less session hashes (300 active, ~19k stale) until Redis refuses writes.
- `incident-simulator/load_generator.py`: seeded, fixed-rate (open-loop) load with p50/p95/p99,
  error-rate and hit-ratio report. Measured: p95 13 ms healthy → ~7 s during incident → 13–20 ms after restore.
- Simulator test suite (31 tests, 98% coverage).

### Changed — Phase 2
- Redis eviction policy `allkeys-lru` → `volatile-lru` (required for the incident to reproduce;
  recreate the container: `docker compose up -d --force-recreate redis`).
- `SLOW_QUERY_MS` default 120 → 250 ms, to make cache-miss cost clearly visible.
- product-api logs rejected cache writes as a one-line WARNING (`cache write rejected`) instead of an
  ERROR with traceback, keeping logs readable under saturation.

### Added — Phase 0 & 1 (2026-09-27)
- Repository foundation: `.gitignore`, `.env.example`, README, docs.
- `product-api`: FastAPI service with `GET /health`, `GET /products`, `GET /products/{id}`, `GET /metrics`.
- Cache-aside product lookups via Redis (`X-Cache: HIT|MISS` header); PostgreSQL with deterministic seed data.
- Simulated query cost on cache misses (`SLOW_QUERY_MS`) so cache health visibly affects latency.
- Prometheus metrics: request count, 5xx errors, latency histogram, cache hits/misses,
  Redis memory used/max/utilization, evicted keys.
- Structured JSON logs; WARNING on slow requests and on Redis memory pressure (≥ 90%).
- Redis capped at 32 MB so cache saturation is reproducible.
- Docker Compose stack (redis, postgres, product-api) with health checks; host ports 8001/5433/6380.
- Unit + integration test suite (pytest, 80% coverage gate).
