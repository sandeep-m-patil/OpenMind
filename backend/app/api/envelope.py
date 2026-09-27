"""Response envelope {data, meta, error} used by every endpoint."""
from fastapi import Request


def envelope(data=None, meta: dict | None = None, error: dict | None = None) -> dict:
    return {"data": data, "meta": meta or {}, "error": error}


def container(request: Request):
    return request.app.state.container
