import fakeredis
import pytest
import redis

from scenarios import cache_pressure as cp
from tests.conftest import CappedRedis

NOW = 1_800_000_000


def test_session_keys_are_deterministic():
    assert cp.session_key("stale", 7) == cp.session_key("stale", 7)


def test_session_keys_do_not_reveal_staleness():
    assert "stale" not in cp.session_key("stale", 7)


def test_inject_fills_redis_until_it_refuses_writes(capped_redis):
    result = cp.inject(capped_redis, now=NOW)

    assert result == cp.InjectResult(active_written=300, stale_written=700, is_saturated=True)


def test_injected_sessions_have_no_ttl(capped_redis):
    cp.inject(capped_redis, now=NOW)

    assert capped_redis.store.ttl(cp.session_key("stale", 0)) == -1


def test_top_up_fills_headroom_left_by_pipeline_buffers():
    class BufferedRedis(CappedRedis):
        """Pipelines hit OOM 50 keys early (their input buffer counts as memory); single writes don't."""

        def pipeline(self, transaction=True):
            self.capacity_keys -= 50
            pipe = super().pipeline(transaction)
            original = pipe.execute

            def execute(raise_on_error=True):
                results = original(raise_on_error)
                self.capacity_keys += 50
                return results

            pipe.execute = execute
            return pipe

    result = cp.inject(BufferedRedis(capacity_keys=1000), now=NOW)

    assert result.active_written + result.stale_written == 1000


def test_saturation_during_active_phase_writes_no_stale_sessions():
    result = cp.inject(CappedRedis(capacity_keys=100), now=NOW)

    assert (result.active_written, result.stale_written, result.is_saturated) == (100, 0, True)


def test_inject_reports_unsaturated_when_redis_never_fills(monkeypatch):
    monkeypatch.setattr(cp, "MAX_STALE_SESSIONS", 50)

    result = cp.inject(fakeredis.FakeRedis(decode_responses=True), now=NOW)

    assert (result.stale_written, result.is_saturated) == (50, False)


def test_non_memory_errors_are_raised():
    class WrongTypeRedis(CappedRedis):
        def apply(self, key, fields):
            return redis.ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")

    with pytest.raises(redis.ResponseError, match="WRONGTYPE"):
        cp.inject(WrongTypeRedis(), now=NOW)


def test_sessions_are_classified_by_last_seen(capped_redis):
    cp.inject(capped_redis, now=NOW)

    assert cp.count_sessions(capped_redis, now=NOW) == (300, 700)


def test_sessions_without_last_seen_are_ignored(capped_redis):
    capped_redis.store.hset("session:odd", mapping={"user_id": "x"})

    assert cp.count_sessions(capped_redis, now=NOW) == (0, 0)


def test_status_reports_memory_policy_and_sessions(capped_redis):
    cp.inject(capped_redis, now=NOW)

    state = cp.status(capped_redis, now=NOW)

    assert (state.utilization, state.policy, state.stale_sessions) == (1000 / 32 / 32, "volatile-lru", 700)


def test_status_policy_is_unknown_when_config_is_disabled(capped_redis, monkeypatch):
    def refuse(_name):
        raise redis.ResponseError("unknown command 'CONFIG'")

    monkeypatch.setattr(capped_redis, "config_get", refuse)

    assert cp.status(capped_redis, now=NOW).policy == "unknown"


def test_utilization_is_zero_without_memory_limit():
    assert cp.CacheStatus(10, 0, 0, "noeviction", 0, 0).utilization == 0.0


def test_restore_removes_sessions_but_keeps_product_cache(capped_redis):
    capped_redis.store.set("product:1", "{}")
    cp.inject(capped_redis, now=NOW)

    deleted = cp.restore(capped_redis)

    assert (deleted, capped_redis.store.exists("product:1")) == (999, 1)
