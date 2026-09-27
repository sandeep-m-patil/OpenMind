"""The scripts Ansible runs (infrastructure/ansible/scripts), tested directly."""
import json

import fakeredis
import httpx

import cleanup_stale_sessions
import flush_cache
import restart_service
import rollback_deployment

NOW = 1_800_000_000
HOUR = 3600


def _redis_with_sessions():
    client = fakeredis.FakeRedis(decode_responses=True)
    client.hset("session:active", mapping={"last_seen": NOW - 60})
    client.hset("session:stale", mapping={"last_seen": NOW - 72 * HOUR})
    client.set("product:1", "{}", ex=300)
    client.info = lambda section: {"used_memory": 1024, "maxmemory": 32 * 1024 * 1024}  # fakeredis has no INFO
    return client


def test_cleanup_deletes_only_stale_sessions():
    client = _redis_with_sessions()

    report = cleanup_stale_sessions.cleanup(client, 24, is_dry_run=False, now=NOW)

    assert (report["sessions_deleted"], sorted(client.keys())) == (1, ["product:1", "session:active"])


def test_cleanup_dry_run_deletes_nothing():
    client = _redis_with_sessions()

    report = cleanup_stale_sessions.cleanup(client, 24, is_dry_run=True, now=NOW)

    assert (report["sessions_stale"], client.dbsize()) == (1, 3)


def test_flush_removes_everything_including_sessions():
    client = _redis_with_sessions()

    assert (flush_cache.flush(client, is_dry_run=False)["keys_deleted"], client.dbsize()) == (3, 0)


def test_flush_dry_run_only_counts():
    assert flush_cache.flush(_redis_with_sessions(), is_dry_run=True)["keys_after"] == 3


def _docker(seen):
    def handle(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(204 if request.method == "POST" else 200, json={"State": {"Status": "running"}})

    return httpx.MockTransport(handle)


def test_restart_targets_only_the_allowlisted_container():
    seen = []
    restart_service.restart("product-api", is_dry_run=False, transport=_docker(seen))

    assert ("POST", "/containers/opsmind-product-api-1/restart") in seen


def test_restart_dry_run_does_not_post():
    seen = []
    restart_service.restart("product-api", is_dry_run=True, transport=_docker(seen))

    assert all(method == "GET" for method, _ in seen)


def test_rollback_triggers_jenkins_job():
    seen = []

    def handle(request):
        seen.append((request.method, request.url.path, request.headers.get("Jenkins-Crumb")))
        if request.url.path == "/crumbIssuer/api/json":
            return httpx.Response(200, json={"crumbRequestField": "Jenkins-Crumb", "crumb": "abc"})
        return httpx.Response(201, headers={"location": "http://jenkins/queue/item/7/"}, json={})

    report = rollback_deployment.rollback("product-api", is_dry_run=False, transport=httpx.MockTransport(handle))

    assert (seen[-1], report["queue_item"]) == (("POST", "/job/product-api-rollback/build", "abc"), "http://jenkins/queue/item/7/")


def test_rollback_works_when_csrf_is_disabled():
    def handle(request):
        return httpx.Response(404 if "crumbIssuer" in request.url.path else 201, json={})

    assert rollback_deployment.rollback("product-api", False, httpx.MockTransport(handle))["job"] == "product-api-rollback"


def test_script_cli_writes_result_file(tmp_path, monkeypatch):
    monkeypatch.setattr(flush_cache.redis.Redis, "from_url", lambda *a, **k: _redis_with_sessions())
    result = tmp_path / "r.json"

    code = flush_cache.main(["--redis-url", "redis://x", "--result-file", str(result), "--dry-run"])

    assert (code, json.loads(result.read_text())["dry_run"]) == (0, True)


def test_cleanup_cli_requires_explicit_mode(tmp_path):
    try:
        cleanup_stale_sessions.main(["--redis-url", "redis://x", "--max-idle-hours", "24", "--result-file", "x"])
    except SystemExit as exc:
        assert exc.code == 2
