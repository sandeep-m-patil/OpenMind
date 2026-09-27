"""Catalog of pre-approved runbooks (runbooks/*.yml). The LLM may only pick an ID from here.

Parameters are validated against each runbook's declared type / bounds / enum, so even a
human-modified action can't pass arbitrary values to the executor.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")
_TYPES = {"integer": int, "string": str, "boolean": bool}


class InvalidRunbook(ValueError):
    pass


@dataclass(frozen=True)
class Runbook:
    id: str
    title: str
    strategy: str
    category: str
    risk: str
    description: str
    playbook: str
    parameters: dict[str, dict] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "strategy": self.strategy,
            "category": self.category,
            "risk": self.risk,
            "description": self.description,
            "parameters": self.parameters,
        }


def _coerce(name: str, spec: dict, value: Any) -> Any:
    expected = _TYPES[spec["type"]]
    if expected is int and isinstance(value, str) and value.lstrip("-").isdigit():
        value = int(value)
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise InvalidRunbook(f"parameter {name} must be {spec['type']}")
    is_below = "min" in spec and value < spec["min"]
    is_above = "max" in spec and value > spec["max"]
    if is_below or is_above:
        raise InvalidRunbook(f"parameter {name}={value} outside [{spec.get('min')}, {spec.get('max')}]")
    if "enum" in spec and value not in spec["enum"]:
        raise InvalidRunbook(f"parameter {name}={value!r} not in {spec['enum']}")
    return value


def validate_params(runbook: Runbook, params: dict | None) -> dict:
    params = params or {}
    unknown = set(params) - set(runbook.parameters)
    if unknown:
        raise InvalidRunbook(f"unknown parameters for {runbook.id}: {sorted(unknown)}")
    return {
        name: _coerce(name, spec, params.get(name, spec.get("default")))
        for name, spec in runbook.parameters.items()
    }


class RunbookCatalog:
    def __init__(self, runbooks: list[Runbook]) -> None:
        self._runbooks = {r.id: r for r in runbooks}

    @classmethod
    def load(cls, directory: str) -> "RunbookCatalog":
        runbooks = []
        for path in sorted(Path(directory).glob("RB-*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if raw.get("risk") not in RISK_LEVELS:
                raise InvalidRunbook(f"{path.name}: risk must be one of {RISK_LEVELS}")
            runbooks.append(Runbook(**{k: raw[k] for k in Runbook.__dataclass_fields__ if k in raw}))
        return cls(runbooks)

    def get(self, runbook_id: str) -> Runbook:
        if runbook_id not in self._runbooks:
            raise InvalidRunbook(f"unknown runbook {runbook_id!r}")
        return self._runbooks[runbook_id]

    def has(self, runbook_id: str | None) -> bool:
        return runbook_id in self._runbooks

    def all(self) -> list[Runbook]:
        return list(self._runbooks.values())
