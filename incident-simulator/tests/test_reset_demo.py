import subprocess

import httpx

import reset_demo
from tests.conftest import CappedRedis


def _install(monkeypatch, delete_status=200):
    calls = {"sql": [], "delete": []}
    monkeypatch.setattr(reset_demo.redis.Redis, "from_url", lambda *a, **k: CappedRedis())
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls["sql"].append(cmd))

    def fake_delete(url, timeout):
        calls["delete"].append(url)
        return httpx.Response(delete_status, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(reset_demo.httpx, "delete", fake_delete)
    return calls


def test_refuses_without_confirmation(monkeypatch):
    calls = _install(monkeypatch)

    assert (reset_demo.main([]), calls["sql"], calls["delete"]) == (1, [], [])


def test_clears_database_and_hindsight_bank(monkeypatch):
    calls = _install(monkeypatch)

    reset_demo.main(["--yes", "--bank", "opsmind-sre"])

    assert (calls["sql"][0][-1], calls["delete"]) == (
        reset_demo.RESET_SQL, ["http://127.0.0.1:8888/v1/default/banks/opsmind-sre/memories"])


def test_missing_bank_is_fine(monkeypatch):
    _install(monkeypatch, delete_status=404)

    assert reset_demo.main(["--yes"]) == 0
