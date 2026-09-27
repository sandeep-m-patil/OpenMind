"""/v1/incidents — list, detail, manual trigger, and human decisions."""
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.envelope import container, envelope
from app.schemas.alerts import ManualIncidentIn
from app.schemas.decisions import DecisionIn
from app.services.decisions import DecisionError
from app.services.workflow import Conflict, NotFound

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
INCIDENT_ID_PATTERN = r"^INC-\d{1,9}$"


def _summary(row: dict) -> dict:
    state = row["state"]
    return {
        "id": row["id"], "service": row["service"], "severity": row["severity"], "title": row["title"],
        "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        "category": (state.get("diagnosis") or {}).get("category"),
        "confidence": state.get("confidence"),
        "recommended_runbook": state.get("recommended_runbook"),
        "final_runbook": (state.get("final_action") or {}).get("runbook_id"),
        "decision": (state.get("human_decision") or {}).get("decision"),
        "historical_matches": (state.get("memory_guidance") or {}).get("matched_incidents", []),
    }


@router.get("")
def list_incidents(request: Request, limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
                   before: str | None = Query(None, pattern=INCIDENT_ID_PATTERN)):
    rows = container(request).incidents.list(limit, before)
    next_cursor = rows[-1]["id"] if len(rows) == limit else None
    return envelope([_summary(r) for r in rows], {"count": len(rows), "next_cursor": next_cursor})


@router.post("", status_code=202)
def create_incident(payload: ManualIncidentIn, request: Request):
    incident_id, is_new = container(request).runner.open_incident(
        service=payload.service, severity=payload.severity, title=payload.title, symptoms=payload.symptoms)
    return envelope({"id": incident_id, "is_new": is_new})


@router.get("/{incident_id}")
def get_incident(incident_id: str, request: Request):
    row = container(request).incidents.get(incident_id)
    if row is None:
        raise HTTPException(404, "incident not found")
    return envelope({**_summary(row), "state": row["state"]})


@router.post("/{incident_id}/decisions", status_code=202)
def decide(incident_id: str, payload: DecisionIn, request: Request):
    try:
        resolved = container(request).runner.decide(incident_id, payload)
    except NotFound:
        raise HTTPException(404, "incident not found") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except DecisionError as exc:
        raise HTTPException(422, str(exc)) from None
    return envelope(resolved)
