import httpx
import pytest

import load_generator as lg

FAST_RATE = 400
SHORT_DURATION = 0.05  # -> 20 requests


def _transport(status: int = 200, cache: str = "HIT", seen: list | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.url.path)
        return httpx.Response(status, headers={"x-cache": cache}, json={})

    return httpx.MockTransport(handle)


def _options(transport: httpx.BaseTransport) -> lg.LoadOptions:
    return lg.LoadOptions(duration_seconds=SHORT_DURATION, rate_per_second=FAST_RATE, transport=transport)


def test_percentile_uses_nearest_rank():
    assert (lg.percentile([10, 20, 30, 40], 50), lg.percentile([10, 20, 30, 40], 95)) == (20, 40)


def test_percentile_of_no_data_is_zero():
    assert lg.percentile([], 95) == 0.0


def test_run_load_sends_rate_times_duration_requests():
    assert len(lg.run_load(_options(_transport()))) == 20


def test_same_seed_sends_the_same_request_sequence():
    first, second = [], []
    lg.run_load(_options(_transport(seen=first)))
    lg.run_load(_options(_transport(seen=second)))

    assert sorted(first) == sorted(second)


def test_server_errors_are_counted():
    report = lg.summarize(lg.run_load(_options(_transport(status=503))), elapsed_seconds=1)

    assert report["error_rate"] == 1.0


def test_connection_failures_are_counted_as_errors():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    samples = lg.run_load(_options(httpx.MockTransport(refuse)))

    assert all(s.is_error for s in samples)


def test_summary_reports_hit_ratio():
    samples = [lg.Sample(5, False, "HIT"), lg.Sample(300, False, "MISS")]

    assert lg.summarize(samples, elapsed_seconds=1)["hit_ratio"] == 0.5


def test_summary_of_no_samples_is_all_zero():
    assert lg.summarize([], elapsed_seconds=0)["rps"] == 0.0


def test_warm_up_touches_every_product_once():
    seen = []
    lg.warm_up(_options(_transport(seen=seen)))

    assert len(set(seen)) == lg.PRODUCT_ID_MAX


def test_main_prints_report(monkeypatch, capsys):
    transport = _transport()
    real_client = lg._client
    monkeypatch.setattr(lg, "_client", lambda options: real_client(lg.LoadOptions(transport=transport)))

    exit_code = lg.main(["--duration", "0.05", "--rate", "100", "--no-warmup"])

    assert (exit_code, "cache hit : 100.0%" in capsys.readouterr().out) == (0, True)


def test_main_rejects_non_positive_rate():
    with pytest.raises(SystemExit):
        lg.main(["--rate", "0"])
