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
from app.core.errors import AIUnavailableError, RepoLensError
from app.schemas.ai import AIStatus, AISummary
from app.schemas.report import AnalysisReport, AnalyzeRequest
from app.schemas.repository import RepositoryMetadata
from app.services.ai.summarizer import summarize
from app.services.analysis_service import run_analysis
from app.services.repository_parser import parse_repository_url
from app.services.snapshot import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
    """Reuse a report produced within the cache TTL for the same repository."""
    key = parse_repository_url(repository_url).full_name.lower()
    cache = request.app.state.report_cache
    cached = cache.get(key)
    if cached is not None:
        await progress("analyze", "Using a report generated in the last few minutes")
        return cached
    report = await run_analysis(repository_url, http, settings, progress)
    cache.set(key, report)
    cache.set(report.repository.full_name.lower(), report)  # canonical name after renames
    return report


@router.post("/analyze", response_model=AnalysisReport)
async def analyze(
    body: AnalyzeRequest, request: Request, http: HttpDep, settings: SettingsDep
) -> AnalysisReport:
    """Analyze a public repository and return the complete report."""
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
    report = await cached_analysis(request, body.repository_url, http, settings)
    key = f"{report.repository.full_name.lower()}@{report.analysis.commit_sha}"
    cached = request.app.state.ai_cache.get(key)
    if cached is not None:
        return cached
    summary = await summarize(report, provider)
    request.app.state.ai_cache.set(key, summary)
    return summary
