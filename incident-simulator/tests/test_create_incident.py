import httpx
import pytest
import redis

import create_incident
from tests.conftest import CappedRedis


@pytest.fixture
def posted(monkeypatch):
    """Capture deploy-event POSTs instead of calling a real OpsMind backend."""
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr(create_incident.httpx, "post", fake_post)
    return calls


@pytest.fixture
def use_redis(monkeypatch, posted):
    def install(client):
        monkeypatch.setattr(create_incident.redis.Redis, "from_url", lambda *a, **k: client)
        return client

    return install


def test_inject_records_the_story_deployment_in_opsmind(use_redis, posted):
    use_redis(CappedRedis())

    create_incident.main(["--type", "cache"])

    assert (posted[0][0], posted[0][1]["service"]) == ("http://127.0.0.1:8002/v1/deployments", "auth-service")


def test_deploy_event_can_be_skipped(use_redis, posted):
    use_redis(CappedRedis())

    create_incident.main(["--type", "cache", "--no-deploy-event"])

    assert posted == []


def test_unreachable_opsmind_does_not_block_the_incident(use_redis, monkeypatch, capsys):
    def refuse(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(create_incident.httpx, "post", refuse)
    use_redis(CappedRedis())

    exit_code = create_incident.main(["--type", "cache"])

    assert (exit_code, "could not record deployment" in capsys.readouterr().out) == (0, True)


def test_inject_command_reports_saturation(use_redis, capsys):
    use_redis(CappedRedis())

    exit_code = create_incident.main(["--type", "cache"])

    assert exit_code == 0
    assert "300 active + 700 stale sessions" in capsys.readouterr().out


def test_status_command_does_not_modify_redis(use_redis):
    client = use_redis(CappedRedis())

    create_incident.main(["--type", "cache", "--status"])

    assert client.store.dbsize() == 0


def test_restore_command_removes_injected_sessions(use_redis):
    client = use_redis(CappedRedis())
    create_incident.main(["--type", "cache"])

    create_incident.main(["--type", "cache", "--restore"])

    assert client.store.dbsize() == 0


def test_warns_when_eviction_policy_prevents_the_incident(use_redis, capsys):
    use_redis(CappedRedis(policy="allkeys-lru"))

    create_incident.main(["--type", "cache", "--status"])

    assert "expected volatile-lru" in capsys.readouterr().out


def test_notes_when_redis_never_fills(use_redis, capsys, monkeypatch):
    monkeypatch.setattr(create_incident.cache_pressure, "MAX_STALE_SESSIONS", 10)
    use_redis(CappedRedis(capacity_keys=10_000))

    create_incident.main(["--type", "cache"])

    assert "never filled up" in capsys.readouterr().out


def test_unreachable_redis_exits_with_clear_message(use_redis, capsys):
    class DownRedis:
        def ping(self):
            raise redis.ConnectionError("connection refused")

    use_redis(DownRedis())

    exit_code = create_incident.main(["--type", "cache"])

    assert (exit_code, "Is the stack running?" in capsys.readouterr().err) == (2, True)


def test_unknown_incident_type_is_rejected():
    with pytest.raises(SystemExit):
        create_incident.main(["--type", "disk"])
