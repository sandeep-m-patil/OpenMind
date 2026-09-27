"""Read-only views: runbook catalog, strategy scores, Hindsight memory search, deployments."""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.envelope import container, envelope
from app.schemas.deployments import DeploymentIn
from app.services.memory import MemoryUnavailable

router = APIRouter(prefix="/v1", tags=["knowledge"])
MAX_QUERY_LENGTH = 500
DEFAULT_LOOKBACK_MINUTES = 24 * 60
MAX_LOOKBACK_MINUTES = 30 * 24 * 60


@router.get("/runbooks")
def list_runbooks(request: Request):
    return envelope([r.summary() for r in container(request).catalog.all()])


@router.get("/strategies")
def list_strategies(request: Request):
    return envelope(container(request).strategies.all())


@router.get("/memories")
def search_memories(request: Request, query: str = Query(min_length=2, max_length=MAX_QUERY_LENGTH),
                    service: str | None = Query(None, pattern=r"^[a-z0-9-]{1,63}$")):
    tags = [f"service:{service}"] if service else None
    try:
        memories = container(request).memory.recall(query, tags=tags)
    except MemoryUnavailable as exc:
        raise HTTPException(503, f"Hindsight unavailable: {exc}") from None
    return envelope([asdict(m) for m in memories], {"count": len(memories)})


@router.post("/deployments", status_code=201)
def record_deployment(payload: DeploymentIn, request: Request):
    return envelope(container(request).deployments.add(payload))


@router.get("/deployments")
def list_deployments(request: Request,
                     lookback_minutes: int = Query(DEFAULT_LOOKBACK_MINUTES, ge=1, le=MAX_LOOKBACK_MINUTES)):
    return envelope(container(request).deployments.recent(lookback_minutes))
