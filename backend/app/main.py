"""OpsMind backend: FastAPI + LangGraph SRE copilot."""
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import alerts, incidents, knowledge
from app.api.envelope import container, envelope
from app.config import Settings, load_settings
from app.container import build_container
from app.logging_setup import configure_logging

logger = logging.getLogger("opsmind")
HTTP_UNPROCESSABLE = 422


def create_app(factory: Callable[[Settings], object] = build_container) -> FastAPI:
    configure_logging()
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = factory(settings)
        logger.info("opsmind backend started", extra={"event": "startup"})
        yield
        app.state.container.close()

    app = FastAPI(title="OpsMind", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse(envelope(error={"message": exc.detail}), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(envelope(error={"message": "invalid request", "details": details}),
                            status_code=HTTP_UNPROCESSABLE)

    @app.get("/health")
    def health(request: Request):
        c = container(request)
        return envelope({
            "status": "ok",
            "components": {
                "prometheus": "up" if c.prometheus.is_reachable() else "down",
                "hindsight": "up" if c.memory.is_available() else "down",
                "llm": "configured" if c.llm.is_configured else "not configured (rule engine)",
                "slack": "enabled" if getattr(c.notifier, "is_enabled", False) else "disabled (dashboard approval)",
            },
        })

    for router in (alerts.router, incidents.router, knowledge.router):
        app.include_router(router)
    return app


app = create_app()
