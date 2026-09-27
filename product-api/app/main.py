"""product-api: a small, intentionally instrumented shop service that OpsMind watches."""
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import Settings, load_settings
from app.dependencies import Dependencies, build_dependencies
from app.logging_setup import configure_logging
from app.metrics import refresh_redis_gauges
from app.middleware import RequestObserver

MAX_PRODUCT_ID = 1_000_000
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
HTTP_OK = 200
HTTP_UNPROCESSABLE = 422
HTTP_SERVICE_UNAVAILABLE = 503

logger = logging.getLogger("product_api")


def _envelope(data=None, meta=None, error=None) -> dict:
    return {"data": data, "meta": meta or {}, "error": error}


def create_app(factory: Callable[[Settings], Dependencies] = build_dependencies) -> FastAPI:
    settings = load_settings()
    configure_logging(settings.service_name, settings.log_level, settings.log_file)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.deps = factory(settings)
        logger.info("product-api started", extra={"event": "startup"})
        yield
        app.state.deps.close()

    app = FastAPI(title="product-api", lifespan=lifespan)
    app.middleware("http")(RequestObserver(settings.slow_request_ms))
    _register_error_handlers(app)
    _register_routes(app, settings)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse(_envelope(error={"message": exc.detail}), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        error = {"message": "invalid request", "details": exc.errors()}
        return JSONResponse(_envelope(error=error), status_code=HTTP_UNPROCESSABLE)


def _register_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/health")
    def health(request: Request):
        deps = request.app.state.deps
        components = {"redis": deps.cache.ping(), "postgres": deps.repo.ping()}
        is_healthy = all(components.values())
        data = {
            "status": "ok" if is_healthy else "degraded",
            "components": {name: "up" if is_up else "down" for name, is_up in components.items()},
        }
        status_code = HTTP_OK if is_healthy else HTTP_SERVICE_UNAVAILABLE
        return JSONResponse(_envelope(data=data), status_code=status_code)

    @app.get("/products")
    def list_products(
        request: Request,
        response: Response,
        limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    ):
        products, cache_status = request.app.state.deps.service.list_products(limit)
        response.headers["X-Cache"] = cache_status
        return _envelope(data=products, meta={"count": len(products), "cache": cache_status})

    @app.get("/products/{product_id}")
    def get_product(request: Request, response: Response, product_id: int = Path(ge=1, le=MAX_PRODUCT_ID)):
        product, cache_status = request.app.state.deps.service.get_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="product not found")
        response.headers["X-Cache"] = cache_status
        return _envelope(data=product, meta={"cache": cache_status})

    @app.get("/metrics")
    def metrics(request: Request):
        refresh_redis_gauges(request.app.state.deps.cache, settings.memory_warn_ratio)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app = create_app()
