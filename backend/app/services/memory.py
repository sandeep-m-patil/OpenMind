"""Thin client for self-hosted Hindsight (github.com/vectorize-io/hindsight), HTTP API v1.

    memory.retain([...])  -> POST /v1/default/banks/{bank}/memories
    memory.recall(query)  -> POST /v1/default/banks/{bank}/memories/recall

We deliberately do NOT build our own vector store or re-rank on top: Hindsight owns memory.
"""
import logging
from dataclasses import asdict, dataclass, field

import httpx

logger = logging.getLogger("opsmind.memory")

REQUEST_TIMEOUT_SECONDS = 60  # retain may run LLM fact extraction when a provider is configured
RECALL_BUDGET = "mid"
RECALL_MAX_TOKENS = 4096
MAX_MEMORIES = 6
MIN_SCORE = 0.05
HTTP_NOT_FOUND = 404


class MemoryUnavailable(RuntimeError):
    """Hindsight could not be reached or returned an error."""


@dataclass
class MemoryItem:
    content: str
    context: str
    document_id: str
    metadata: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    timestamp: str | None = None

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload["metadata"] = {k: str(v) for k, v in self.metadata.items()}
        return {k: v for k, v in payload.items() if v is not None}


@dataclass
class RecalledMemory:
    id: str
    text: str
    score: float
    document_id: str | None
    metadata: dict[str, str]
    tags: list[str]
    type: str | None


class MemoryService:
    def __init__(self, base_url: str, bank_id: str, transport: httpx.BaseTransport | None = None) -> None:
        self._bank_path = f"/v1/default/banks/{bank_id}"
        self._client = httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport)

    def is_available(self) -> bool:
        try:
            return self._client.get("/health").status_code == httpx.codes.OK
        except httpx.HTTPError:
            return False

    def _post(self, path: str, body: dict) -> httpx.Response:
        try:
            return self._client.post(self._bank_path + path, json=body)
        except httpx.HTTPError as exc:
            raise MemoryUnavailable(f"hindsight unreachable: {exc}") from exc

    def retain(self, items: list[MemoryItem]) -> dict:
        response = self._post("/memories", {"items": [i.to_payload() for i in items], "async": False})
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise MemoryUnavailable(f"retain failed: HTTP {response.status_code} {response.text[:200]}")
        logger.info("retained memories", extra={"event": "memory_retain", "items": len(items)})
        return response.json()

    def recall(self, query: str, tags: list[str] | None = None) -> list[RecalledMemory]:
        body: dict = {"query": query, "budget": RECALL_BUDGET, "max_tokens": RECALL_MAX_TOKENS}
        if tags:
            body.update(tags=tags, tags_match="any_strict")
        response = self._post("/memories/recall", body)
        if response.status_code == HTTP_NOT_FOUND:
            return []  # bank doesn't exist yet: nothing has been retained
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise MemoryUnavailable(f"recall failed: HTTP {response.status_code} {response.text[:200]}")
        memories = [_to_memory(r) for r in response.json().get("results", [])]
        relevant = [m for m in memories if m.score >= MIN_SCORE]
        logger.info("recalled memories", extra={"event": "memory_recall", "count": len(relevant)})
        return relevant[:MAX_MEMORIES]


def _to_memory(result: dict) -> RecalledMemory:
    scores = result.get("scores") or {}
    return RecalledMemory(
        id=result["id"],
        text=result["text"],
        score=float(scores.get("final") or 0.0),
        document_id=result.get("document_id"),
        metadata=result.get("metadata") or {},
        tags=result.get("tags") or [],
        type=result.get("type"),
    )
