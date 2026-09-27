"""Runs an approved runbook through Ansible. Never executes LLM text.

The command line is built only from: a fixed playbook path taken from the catalog, and parameters
that already passed validation — passed as a JSON extra-vars document, never through a shell.
Every run is a dry-run (`--check`) first; the real run happens only if the dry run succeeds.
"""
import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.runbooks import Runbook

logger = logging.getLogger("opsmind.executor")

STDOUT_TAIL_CHARS = 6000
TIMEOUT_RETURN_CODE = -1


@dataclass
class ExecutionResult:
    runbook_id: str
    mode: str  # "check" or "apply"
    is_success: bool
    return_code: int
    is_timed_out: bool
    duration_seconds: float
    command: list[str]
    output_tail: str
    result: dict | None  # structured report written by the runbook script

    def to_dict(self) -> dict:
        return asdict(self)


class AnsibleExecutor:
    def __init__(self, ansible_dir: str, timeout_seconds: int) -> None:
        self._dir = Path(ansible_dir)
        self._timeout = timeout_seconds

    def playbook_path(self, runbook: Runbook) -> Path:
        path = (self._dir / "playbooks" / runbook.playbook).resolve()
        if self._dir.resolve() not in path.parents or not path.is_file():
            raise FileNotFoundError(f"playbook for {runbook.id} not found: {runbook.playbook}")
        return path

    def run(self, runbook: Runbook, params: dict, is_check: bool) -> ExecutionResult:
        with tempfile.TemporaryDirectory(prefix="opsmind-") as work:
            result_file = Path(work) / "result.json"
            extra_vars = {**params, "opsmind_result_file": str(result_file)}
            command = [
                "ansible-playbook",
                "-i", str(self._dir / "inventory.ini"),
                str(self.playbook_path(runbook)),
                "--extra-vars", json.dumps(extra_vars),
            ] + (["--check"] if is_check else [])
            start = time.monotonic()
            return_code, output, is_timed_out = self._invoke(command)
            report = json.loads(result_file.read_text()) if result_file.is_file() else None
        result = ExecutionResult(
            runbook_id=runbook.id,
            mode="check" if is_check else "apply",
            is_success=return_code == 0 and not is_timed_out,
            return_code=return_code,
            is_timed_out=is_timed_out,
            duration_seconds=round(time.monotonic() - start, 2),
            command=command,
            output_tail=output[-STDOUT_TAIL_CHARS:],
            result=report,
        )
        logger.info("runbook executed", extra={"event": "runbook_run", "runbook": runbook.id,
                                               "mode": result.mode, "success": result.is_success})
        return result

    def _invoke(self, command: list[str]) -> tuple[int, str, bool]:
        try:
            completed = subprocess.run(  # noqa: S603 — argv list, no shell, fixed executable
                command, capture_output=True, text=True, timeout=self._timeout, cwd=self._dir,
                env={"ANSIBLE_NOCOLOR": "1", "ANSIBLE_CONFIG": str(self._dir / "ansible.cfg"),
                     **_passthrough_env()},
            )
            return completed.returncode, completed.stdout + completed.stderr, False
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return TIMEOUT_RETURN_CODE, output + f"\nTIMEOUT after {self._timeout}s", True


def _passthrough_env() -> dict[str, str]:
    """Only the variables the playbooks need (no secrets beyond what each runbook requires)."""
    names = ("PATH", "HOME", "REDIS_URL", "DOCKER_HOST", "JENKINS_URL", "JENKINS_USER", "JENKINS_API_TOKEN")
    return {n: os.environ[n] for n in names if n in os.environ}
