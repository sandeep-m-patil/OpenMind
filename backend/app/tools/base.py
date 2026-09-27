"""Uniform tool contract: every evidence tool returns a ToolResult and never raises.

The agent reports a failed tool as missing evidence ("monitoring unavailable") instead of guessing.
"""
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

logger = logging.getLogger("opsmind.tools")
MS_PER_SECOND = 1000


@dataclass
class ToolResult:
    tool: str
    is_ok: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def run_tool(name: str, fn: Callable[[], Any]) -> ToolResult:
    start = time.perf_counter()
    try:
        data = fn()
        result = ToolResult(tool=name, is_ok=True, data=data)
    except Exception as exc:  # noqa: BLE001 — a tool failure must become evidence, not a crash
        result = ToolResult(tool=name, is_ok=False, error=f"{type(exc).__name__}: {exc}")
    result.duration_ms = round((time.perf_counter() - start) * MS_PER_SECOND, 1)
    level = logging.INFO if result.is_ok else logging.WARNING
    logger.log(level, "tool call", extra={"event": "tool_call", "tool": name, "ok": result.is_ok,
                                          "duration_ms": result.duration_ms, "error": result.error})
    return result
