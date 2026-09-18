"""RepoLens API entry point."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.errors import AIUnavailableError, RepoLensError
from app.core.rate_limit import SlidingWindowLimiter, client_id
from app.services.ai.providers import build_provider
from app.services.cache import TTLCache
from app.services.github_client import build_http_client

logger = logging.getLogger("repolens")
access_log = logging.getLogger("repolens.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


_UNSET = object()


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    ai_provider: object = _UNSET,  # AIProvider | None; _UNSET builds from settings
) -> FastAPI:
    """Build the app. `transport` and `ai_provider` let tests substitute fakes."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http = build_http_client(settings, transport)
        app.state.report_cache = TTLCache(settings.cache_max_entries, settings.cache_ttl_seconds)
        app.state.ai_cache = TTLCache(settings.cache_max_entries, settings.ai_cache_ttl_seconds)
        app.state.analysis_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute, 60)
        app.state.ai_limiter = SlidingWindowLimiter(settings.ai_rate_limit_per_hour, 3600)
        app.state.analysis_slots = asyncio.Semaphore(settings.max_concurrent_analyses)
        app.state.inflight = {}
        if ai_provider is not _UNSET:
            app.state.ai = ai_provider
        else:
            try:
                app.state.ai = build_provider(settings, app.state.http)
            except AIUnavailableError as exc:
                # Misconfigured AI must never take down the deterministic analysis.
                logger.error("AI disabled: %s", exc.message)
                app.state.ai = None
        if app.state.ai is not None:
            logger.info("AI summaries enabled (%s, %s)", app.state.ai.name, app.state.ai.model)
        logger.info(
            "RepoLens API %s started (GitHub token: %s)",
            APP_VERSION,
            "configured" if settings.github_token else "not configured",
        )
        try:
            yield
        finally:
            await app.state.http.aclose()

    app = FastAPI(
        title="RepoLens API",
        version=APP_VERSION,
        description="Deterministic static analysis of public GitHub repositories.",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.max_request_bytes):
            response: Response = JSONResponse(
                status_code=413,
                content=error_body("request_too_large", "Request body is too large."),
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path != "/api/health":
            access_log.info(
                "%s %s %s %.0fms client=%s id=%s",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
                client_id(request, settings),
                request_id,
            )
        return response

    # Reports for large repositories are several hundred KB of JSON; compress them.
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.exception_handler(RepoLensError)
    async def handle_domain_error(_: Request, exc: RepoLensError) -> JSONResponse:
        headers = {}
        retry = exc.details.get("retry_after_seconds")
        if retry is not None:
            headers["Retry-After"] = str(retry)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        message = first.get("msg", "Invalid request.")
        return JSONResponse(status_code=422, content=error_body("invalid_request", message))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "An unexpected error occurred."),
        )

    app.include_router(router)
    return app


app = create_app()
