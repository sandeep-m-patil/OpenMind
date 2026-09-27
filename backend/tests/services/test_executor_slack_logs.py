import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from app.services.executor import AnsibleExecutor
from app.services.runbooks import Runbook, RunbookCatalog
from app.services.slack import NullNotifier, SlackNotifier, handle_interaction
from app.services.slack_messages import finished_text, pending_blocks
from app.tools.base import run_tool
from app.tools.logs import summarize_logs
from tests.fakes import REPO

ANSIBLE_DIR = str(REPO / "infrastructure" / "ansible")
CATALOG = RunbookCatalog.load(str(REPO / "runbooks"))


def _fake_run(return_code=0, report=None, timeout=False):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if timeout:
            raise subprocess.TimeoutExpired(command, 1, output="partial")
        if report is not None:
            extra = json.loads(command[command.index("--extra-vars") + 1])
            with open(extra["opsmind_result_file"], "w") as handle:
                json.dump(report, handle)
        return subprocess.CompletedProcess(command, return_code, stdout="PLAY RECAP ok=1", stderr="")

    return run, calls


def test_dry_run_passes_check_flag_and_json_vars(monkeypatch):
    run, calls = _fake_run(report={"sessions_stale": 5})
    monkeypatch.setattr(subprocess, "run", run)

    result = AnsibleExecutor(ANSIBLE_DIR, 5).run(CATALOG.get("RB-CACHE-001"), {"max_idle_hours": 24}, is_check=True)

    assert (calls[0][-1], result.result, result.mode) == ("--check", {"sessions_stale": 5}, "check")


def test_nonzero_exit_is_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(return_code=2)[0])

    assert AnsibleExecutor(ANSIBLE_DIR, 5).run(CATALOG.get("RB-CACHE-002"), {}, is_check=False).is_success is False


def test_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(timeout=True)[0])

    result = AnsibleExecutor(ANSIBLE_DIR, 5).run(CATALOG.get("RB-CACHE-002"), {}, is_check=False)

    assert (result.is_timed_out, result.is_success) == (True, False)


def test_playbook_outside_ansible_dir_is_refused():
    rogue = Runbook("RB-X-001", "x", "x", "x", "LOW", "x", "../../etc/passwd")

    with pytest.raises(FileNotFoundError):
        AnsibleExecutor(ANSIBLE_DIR, 5).playbook_path(rogue)


def _incident(status="PENDING_APPROVAL"):
    state = {"service": "product-api", "severity": "critical", "title": "High latency", "confidence": 0.92,
             "diagnosis": {"category": "cache_saturation", "rationale": "INC-1001 was resolved"},
             "memory_guidance": {"matched_incidents": ["INC-1001"]}, "recommended_runbook": "RB-CACHE-001",
             "recommended_params": {"max_idle_hours": 24}, "risk": "LOW", "findings": ["Redis 100%"],
             "verification_result": {"before": {"p95_seconds": 7.5}, "after": {"p95_seconds": 0.27}},
             "learning_summary": "prefer RB-CACHE-001"}
    return {"id": "INC-1002", "status": status, "state": state}


def test_pending_message_has_four_actions_and_history():
    blocks = pending_blocks(_incident(), "http://dash")
    actions = [e["text"]["text"] for e in blocks[4]["elements"]]

    assert (actions, "INC-1001" in json.dumps(blocks)) == (["Approve", "Edit", "Reject", "Execute manually"], True)


def test_finished_text_shows_before_after_and_lesson():
    text = finished_text(_incident("RESOLVED"))

    assert "7.50s → 0.27s" in text and "prefer RB-CACHE-001" in text


def test_button_click_becomes_a_decision():
    decided, notes = [], []
    payload = {"user": {"username": "sre"}, "actions": [{"action_id": "opsmind_approve", "value": "INC-1"},
                                                        {"action_id": "opsmind_edit", "value": "INC-1"}]}

    handle_interaction(payload, lambda *a: decided.append(a), lambda i, t: notes.append(t))

    assert decided == [("INC-1", "APPROVED", "sre")]


def test_failed_button_click_is_reported_to_channel():
    notes = []

    def refuse(*_):
        raise RuntimeError("already decided")

    handle_interaction({"user": {}, "actions": [{"action_id": "opsmind_reject", "value": "INC-1"}]}, refuse,
                       lambda i, t: notes.append(t))

    assert "already decided" in notes[0]


class FakeWebClient:
    def __init__(self, should_fail=False):
        self.posts, self.should_fail = [], should_fail

    def chat_postMessage(self, **kwargs):
        if self.should_fail:
            raise OSError("network down")
        self.posts.append(kwargs)
        return {"ts": "123.45"}


def test_outcome_is_threaded_under_the_incident_message():
    client = FakeWebClient()
    notifier = SlackNotifier(client, "C1", "http://dash")
    notifier.incident_pending(_incident())
    notifier.incident_finished(_incident("RESOLVED"))

    assert client.posts[1]["thread_ts"] == "123.45"


def test_slack_outage_never_raises():
    SlackNotifier(FakeWebClient(should_fail=True), "C1", "http://dash").incident_pending(_incident())


def test_null_notifier_is_a_no_op():
    NullNotifier().incident_pending(_incident())


def test_log_summary_counts_recent_warnings(tmp_path):
    now = datetime.now(timezone.utc)
    lines = [{"ts": (now - timedelta(minutes=m)).isoformat(), "level": lvl, "msg": msg, "event": "http_request",
              "duration_ms": 900.0} for m, lvl, msg in [(1, "WARNING", "cache write rejected"),
                                                         (2, "WARNING", "cache write rejected"),
                                                         (30, "WARNING", "old"), (1, "INFO", "request")]]
    path = tmp_path / "app.log"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\nnot json\n")

    summary = summarize_logs(str(path), 5, now)

    assert (summary["total_lines"], summary["top_warnings"][0]) == (3, {"message": "WARNING: cache write rejected", "count": 2})


def test_tool_failures_become_results():
    result = run_tool("broken", lambda: 1 / 0)

    assert (result.is_ok, result.error.startswith("ZeroDivisionError")) == (False, True)
