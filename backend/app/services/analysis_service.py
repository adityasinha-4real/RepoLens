"""End-to-end analysis: validate -> collect snapshot -> run analyzers -> assemble report."""

import logging
import time
from datetime import UTC, datetime

import anyio
import httpx

from app.analyzers.architecture_analyzer import analyze_architecture
from app.analyzers.code_analyzer import analyze_code
from app.analyzers.dependency_analyzer import analyze_dependencies
from app.analyzers.documentation_analyzer import analyze_documentation
from app.analyzers.language_analyzer import analyze_languages
from app.analyzers.report_generator import build_health_report
from app.analyzers.security_analyzer import analyze_security
from app.analyzers.structure import analyze_structure
from app.core.config import APP_VERSION, Settings
from app.schemas.report import AnalysisLimits, AnalysisMeta, AnalysisReport, FetchSummary
from app.services.github_client import GitHubClient
from app.services.repository_parser import parse_repository_url
from app.services.snapshot import (
    ProgressCallback,
    RepositorySnapshot,
    collect_snapshot,
    noop_progress,
)

logger = logging.getLogger(__name__)


def build_report(
    snapshot: RepositorySnapshot, settings: Settings, started: float, now: datetime | None = None
) -> AnalysisReport:
    """Run every analyzer over an already-collected snapshot. Pure CPU work, no I/O."""
    tree, contents, meta = snapshot.tree, snapshot.contents, snapshot.metadata
    structure = analyze_structure(tree, repo_name=meta.name, max_file_bytes=settings.max_file_bytes)
    languages = analyze_languages(tree, contents, snapshot.github_languages, meta.primary_language)
    dependencies = analyze_dependencies(tree, contents)
    quality = analyze_code(tree, contents, {d.name for d in dependencies.dependencies})
    documentation = analyze_documentation(tree, contents, meta.license_spdx, meta.license_name)
    security = analyze_security(tree, contents, has_lockfiles=bool(dependencies.lockfiles))
    architecture = analyze_architecture(tree, contents, dependencies.dependencies)
    health = build_health_report(
        metadata=meta,
        head_commit_date=snapshot.head_commit_date,
        structure=structure,
        quality=quality,
        dependencies=dependencies,
        documentation=documentation,
        security=security,
        architecture=architecture,
        now=now,
    )

    stats = snapshot.fetch_stats
    notes = list(tree.notes)
    if stats.budget_exhausted:
        notes.append("The download budget was reached; some selected files were not analyzed.")
    if stats.rate_limited:
        notes.append("GitHub's raw content host rate-limited the download; results are partial.")
    if stats.failed:
        notes.append(f"{stats.failed} selected file(s) could not be downloaded.")
    if structure.oversized_files:
        notes.append(
            f"{structure.oversized_files} file(s) exceed the per-file size limit and "
            "were not downloaded."
        )
    partial = bool(tree.truncated or stats.budget_exhausted or stats.rate_limited or stats.failed)

    return AnalysisReport(
        repository=meta,
        analysis=AnalysisMeta(
            analyzed_at=now or datetime.now(UTC),
            duration_ms=int((time.perf_counter() - started) * 1000),
            commit_sha=tree.commit_sha,
            head_commit_date=snapshot.head_commit_date,
            github_api_calls=snapshot.api_calls,
            rate_limit=snapshot.rate_limit,
            fetch=FetchSummary(
                files_selected=stats.selected,
                files_downloaded=stats.fetched,
                bytes_downloaded=stats.bytes_fetched,
                skipped_binary=stats.skipped_binary,
                skipped_too_large=stats.skipped_too_large,
                failed=stats.failed,
                budget_exhausted=stats.budget_exhausted,
                raw_rate_limited=stats.rate_limited,
            ),
            limits=AnalysisLimits(
                max_tree_entries=settings.max_tree_entries,
                max_files_to_fetch=settings.max_files_to_fetch,
                max_file_bytes=settings.max_file_bytes,
                max_total_fetch_bytes=settings.max_total_fetch_bytes,
            ),
            partial=partial,
            notes=notes,
            engine_version=APP_VERSION,
        ),
        health=health,
        structure=structure,
        languages=languages,
        dependencies=dependencies,
        quality=quality,
        documentation=documentation,
        security=security,
        architecture=architecture,
    )


async def run_analysis(
    repository_url: str,
    http: httpx.AsyncClient,
    settings: Settings,
    progress: ProgressCallback = noop_progress,
) -> AnalysisReport:
    started = time.perf_counter()
    await progress("validate", "Validating repository URL")
    ref = parse_repository_url(repository_url)
    github = GitHubClient(http, settings)
    snapshot = await collect_snapshot(github, http, settings, ref, progress)
    await progress("analyze", "Analyzing structure, dependencies, code and security")
    # Analyzers are CPU-bound; run them off the event loop so other requests stay responsive.
    report = await anyio.to_thread.run_sync(build_report, snapshot, settings, started)
    logger.info(
        "Analyzed %s@%s in %d ms (%d API calls, %d files downloaded)",
        snapshot.ref.full_name,
        snapshot.tree.commit_sha[:12],
        report.analysis.duration_ms,
        snapshot.api_calls,
        snapshot.fetch_stats.fetched,
    )
    return report
