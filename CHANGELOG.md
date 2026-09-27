# Changelog

All notable changes to OpsMind. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Docs (2026-09-27)
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
