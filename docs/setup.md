# Setup (Windows 11 + Docker Desktop)

All commands are for **PowerShell**, run from the project folder (`...\Hyd3.0\OpsMind`).

## Prerequisites

| Tool | Check | Needed for |
|---|---|---|
| Docker Desktop (WSL2 backend) | `docker --version` | running everything |
| Python 3.11 | `python --version` | running tests locally |
| Git | `git --version` | version control |

## 1. Configure

```powershell
Copy-Item .env.example .env
```
Creates your private `.env` (git-ignored). Defaults work as-is for local development.

**Ports:** OpsMind uses host ports **8001** (product-api), **5433** (Postgres) and **6380** (Redis),
because 8000/5432/6379 are commonly taken. If one is busy, change `PRODUCT_API_PORT`,
`POSTGRES_HOST_PORT` or `REDIS_HOST_PORT` in `.env`. Find what holds a port with:
```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen
```

## 2. Start the stack

```powershell
docker compose up -d --build
```
`--build` builds the product-api image; `-d` runs in the background. First run downloads images (a few minutes).

```powershell
docker compose ps
```
Expected: `redis`, `postgres`, `product-api` all `Up ... (healthy)`. (product-api takes ~15 s to turn healthy.)

## 3. Verify

```powershell
curl.exe http://localhost:8001/health
```
Expected: `{"data":{"status":"ok","components":{"redis":"up","postgres":"up"}},"meta":{},"error":null}`

```powershell
curl.exe -i http://localhost:8001/products/42
curl.exe -i http://localhost:8001/products/42
```
Expected: first response header `x-cache: MISS` (~260 ms), second `x-cache: HIT` (~3 ms).

```powershell
curl.exe -s http://localhost:8001/metrics | Select-String "^(cache_|redis_memory_util)"
docker compose logs product-api --tail 10
```
Expected: cache hit/miss counters, Redis utilization around `0.03`, and JSON log lines.

> Use `curl.exe`, not `curl` — in Windows PowerShell `curl` is an alias for `Invoke-WebRequest`.

## 4. Run tests

```powershell
cd product-api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```
Unit tests use fakes and need no containers. To also run the integration tests against the live stack:
```powershell
$env:TEST_DATABASE_URL = "postgresql://opsmind:changeme-local-only@localhost:5433/shop"
$env:TEST_REDIS_URL    = "redis://localhost:6380/15"
.\.venv\Scripts\python.exe -m pytest
```
(Use the user/password/ports from your `.env`. Redis DB 15 keeps test keys away from the app's DB 0.)
Expected: `24 passed`, coverage above 80%.

## 5. Incident simulator (Phase 2)

One-time setup (its own virtual environment, so its packages don't mix with product-api's):
```powershell
cd incident-simulator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run from inside `incident-simulator\`:

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python.exe create_incident.py --type cache --status` | Show Redis memory, eviction policy, active/stale sessions |
| `.\.venv\Scripts\python.exe create_incident.py --type cache` | **Inject** cache saturation (~3–5 s) |
| `.\.venv\Scripts\python.exe create_incident.py --type cache --restore` | **Undo** it (removes all injected sessions) |
| `.\.venv\Scripts\python.exe load_generator.py` | Send 50 req/s for 30 s and print p50/p95/p99, errors, hit ratio |
| `.\.venv\Scripts\python.exe -m pytest` | Simulator tests (no containers needed) |

Expected numbers on a typical laptop:

| | Healthy | During cache incident |
|---|---|---|
| p95 latency | ~13–20 ms | ~5–7 s (keeps climbing while load runs) |
| Cache hit ratio | 100% | ~5% |
| Redis memory | ~4% | 100% |

`--status` must show `policy : volatile-lru`. If it shows `allkeys-lru`, your Redis container predates
Phase 2 — run `docker compose up -d --force-recreate redis`.

> **Use `127.0.0.1`, not `localhost`, from Windows scripts.** `localhost` tries IPv6 first, Docker only
> listens on IPv4, and each new connection stalls ~2 s. The simulator defaults already use `127.0.0.1`.

## Stop / reset

```powershell
docker compose down          # stop, keep database data
docker compose down -v       # stop AND delete database data (re-seeded on next start)
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `port is already allocated` | Change the port in `.env`, then `docker compose up -d` |
| `set POSTGRES_USER in .env` | You skipped step 1 |
| product-api `unhealthy` / restarting | `docker compose logs product-api` — usually DB credentials changed after the volume was created; run `docker compose down -v` |
| `/health` shows `postgres: down` | `docker compose ps postgres`; wait for `healthy` |
| Tests: `Connection refused` in `test_live_stack` | Stack not running, or wrong ports in `TEST_*` URLs |
| Simulator: `Cannot reach Redis at ...` | Stack not running (`docker compose ps`) or `REDIS_HOST_PORT` changed — pass `--redis-url` |
| Incident injected but latency normal | Check `--status`: memory must be ~100% and policy `volatile-lru` (see above) |
| Load generator p99 ≈ 2000 ms even when healthy | You passed a `localhost` URL — use `127.0.0.1` |
