import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator

import anyio
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import GitHubDep, HttpDep, SettingsDep
from app.core.config import APP_VERSION, Settings
from app.core.errors import (
    AIUnavailableError,
    AnalysisTimeoutError,
    RepoLensError,
    ServerBusyError,
    TooManyRequestsError,
)
from app.core.rate_limit import client_id
from app.schemas.ai import AIStatus, AISummary
from app.schemas.report import AnalysisReport, AnalyzeRequest
from app.schemas.repository import RepositoryMetadata
from app.services.ai.summarizer import summarize
from app.services.analysis_service import run_analysis
from app.services.repository_parser import parse_repository_url
from app.services.snapshot import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
SLOT_WAIT_SECONDS = 20


class HealthResponse(BaseModel):
    status: str
    version: str
    ai_enabled: bool
    ai: AIStatus


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    provider = request.app.state.ai
    status = AIStatus(
        enabled=provider is not None,
        provider=provider.name if provider else None,
        model=provider.model if provider else None,
    )
    return HealthResponse(status="ok", version=APP_VERSION, ai_enabled=status.enabled, ai=status)


@router.get("/repositories/{owner}/{name}", response_model=RepositoryMetadata)
async def repository_metadata(owner: str, name: str, github: GitHubDep) -> RepositoryMetadata:
    ref = parse_repository_url(f"{owner}/{name}")
    return await github.get_repository(ref)


async def cached_analysis(
    request: Request,
    repository_url: str,
    http: httpx.AsyncClient,
    settings: Settings,
    progress: ProgressCallback = noop_progress,
) -> AnalysisReport:
    """Serve from cache, join an identical analysis already running, or run a new one within
    the instance's concurrency and time limits."""
    state = request.app.state
    key = parse_repository_url(repository_url).full_name.lower()
    cached = state.report_cache.get(key)
    if cached is not None:
        await progress("analyze", "Using a report generated in the last few minutes")
        return cached

    inflight: dict[str, asyncio.Future[AnalysisReport]] = state.inflight
    if key in inflight:
        await progress("analyze", "Joining an identical analysis that is already running")
        return await asyncio.shield(inflight[key])

    future: asyncio.Future[AnalysisReport] = asyncio.get_running_loop().create_future()
    # Retrieve the exception even when nobody joined, so asyncio does not log it as lost.
    future.add_done_callback(lambda f: None if f.cancelled() else f.exception())
    inflight[key] = future
    try:
        try:
            await asyncio.wait_for(state.analysis_slots.acquire(), timeout=SLOT_WAIT_SECONDS)
        except TimeoutError as exc:
            raise ServerBusyError(
                "RepoLens is busy with other analyses. Try again in a minute."
            ) from exc
        try:
            report = await asyncio.wait_for(
                run_analysis(repository_url, http, settings, progress),
                timeout=settings.analysis_timeout_seconds,
            )
        except TimeoutError as exc:
            raise AnalysisTimeoutError(
                "The analysis took too long. Very large repositories may exceed the limit."
            ) from exc
        finally:
            state.analysis_slots.release()
        state.report_cache.set(key, report)
        state.report_cache.set(report.repository.full_name.lower(), report)  # after renames
        future.set_result(report)
        return report
    except asyncio.CancelledError:
        future.set_exception(ServerBusyError("The analysis was interrupted. Please try again."))
        raise
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        inflight.pop(key, None)


def enforce_rate_limit(request: Request, settings: Settings, kind: str) -> None:
    limiter = request.app.state.ai_limiter if kind == "ai" else request.app.state.analysis_limiter
    retry_after = limiter.check(client_id(request, settings))
    if retry_after is not None:
        what = "AI summaries" if kind == "ai" else "analyses"
        raise TooManyRequestsError(
            f"Too many {what} from your address. Try again in {retry_after} seconds.",
            retry_after_seconds=retry_after,
        )


@router.post("/analyze", response_model=AnalysisReport)
async def analyze(
    body: AnalyzeRequest, request: Request, http: HttpDep, settings: SettingsDep
) -> AnalysisReport:
    """Analyze a public repository and return the complete report."""
    enforce_rate_limit(request, settings, "analysis")
    return await cached_analysis(request, body.repository_url, http, settings)


@router.post(
    "/analyze/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": "Newline-delimited JSON events: progress, then result or error.",
        }
    },
)
async def analyze_stream(
    body: AnalyzeRequest, request: Request, http: HttpDep, settings: SettingsDep
) -> StreamingResponse:
    """Same as /analyze, but streams progress events so clients can show the current stage.

    Each line is one JSON object:
      {"type": "progress", "stage": "tree", "message": "..."}
      {"type": "result", "report": {...}}
      {"type": "error", "error": {"code": "...", "message": "...", "details": {...}}}
    """
    enforce_rate_limit(request, settings, "analysis")  # before streaming: a real HTTP 429
    send, receive = anyio.create_memory_object_stream[dict](max_buffer_size=32)

    async def progress(stage: str, message: str) -> None:
        await send.send({"type": "progress", "stage": stage, "message": message})

    async def worker() -> None:
        async with send:
            try:
                report = await cached_analysis(
                    request, body.repository_url, http, settings, progress
                )
                await send.send({"type": "result", "report": report.model_dump(mode="json")})
            except RepoLensError as exc:
                await send.send(
                    {
                        "type": "error",
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                            "status": exc.status_code,
                        },
                    }
                )
            except Exception:
                logger.exception("Unhandled error during streamed analysis")
                await send.send(
                    {
                        "type": "error",
                        "error": {
                            "code": "internal_error",
                            "message": "An unexpected error occurred.",
                            "details": {},
                            "status": 500,
                        },
                    }
                )

    async def events() -> AsyncIterator[str]:
        # A plain task (not a task group): yielding inside a task group from an async
        # generator is unsafe. If the client disconnects, the finally block cancels the work.
        task = asyncio.create_task(worker())
        try:
            async with receive:
                async for event in receive:
                    yield json.dumps(event, separators=(",", ":")) + "\n"
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/ai/summary", response_model=AISummary)
async def ai_summary(
    body: AnalyzeRequest, request: Request, http: HttpDep, settings: SettingsDep
) -> AISummary:
    """Optional AI narrative built from the deterministic report (never from raw code).

    Returns 503 `ai_unavailable` when no provider is configured."""
    provider = request.app.state.ai
    if provider is None:
        raise AIUnavailableError("AI summaries are not enabled on this RepoLens instance.")
    enforce_rate_limit(request, settings, "ai")
    report = await cached_analysis(request, body.repository_url, http, settings)
    key = f"{report.repository.full_name.lower()}@{report.analysis.commit_sha}"
    cached = request.app.state.ai_cache.get(key)
    if cached is not None:
        return cached
    summary = await summarize(report, provider)
    request.app.state.ai_cache.set(key, summary)
    return summary
