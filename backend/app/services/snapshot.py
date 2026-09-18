"""Collect everything the analyzers need from GitHub, in one bounded pass.

After collection the analyzers are pure functions of the snapshot and perform no I/O.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import Settings
from app.schemas.repository import RateLimitInfo, RepositoryMetadata
from app.services.content_fetcher import FetchStats, fetch_contents, select_files
from app.services.github_client import GitHubClient
from app.services.repository_parser import RepoRef
from app.services.repository_tree import RepositoryTree

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], Awaitable[None]]


async def _noop(stage: str, message: str) -> None:
    return None


@dataclass
class RepositorySnapshot:
    ref: RepoRef
    metadata: RepositoryMetadata
    head_commit_date: datetime | None
    tree: RepositoryTree
    contents: dict[str, str]
    fetch_stats: FetchStats
    github_languages: dict[str, int]
    rate_limit: RateLimitInfo
    api_calls: int


async def collect_snapshot(
    github: GitHubClient,
    http: httpx.AsyncClient,
    settings: Settings,
    ref: RepoRef,
    progress: ProgressCallback = _noop,
) -> RepositorySnapshot:
    await progress("metadata", "Fetching repository metadata")
    metadata = await github.get_repository(ref)
    # Use the canonical owner/name (handles renamed repos and case differences).
    ref = RepoRef(metadata.owner, metadata.name)

    await progress("tree", "Fetching repository tree")
    sha, commit_date = await github.get_head_commit(ref, metadata.default_branch)
    tree = await github.get_tree(ref, sha)
    languages = await github.get_languages(ref)

    selected = select_files(tree, settings)
    await progress("contents", f"Downloading {len(selected)} relevant files")
    fetched = await fetch_contents(http, settings, ref, tree, selected)
    stats = fetched.stats
    if stats.failed or stats.rate_limited or stats.budget_exhausted:
        logger.info("Content fetch for %s: %s", ref.full_name, stats)

    return RepositorySnapshot(
        ref=ref,
        metadata=metadata,
        head_commit_date=commit_date,
        tree=tree,
        contents=fetched.files,
        fetch_stats=stats,
        github_languages=languages,
        rate_limit=github.rate_limit.model_copy(),
        api_calls=github.api_calls,
    )
