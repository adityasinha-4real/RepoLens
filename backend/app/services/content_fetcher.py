"""Decide which files to download and fetch them within strict limits.

Selection is deterministic and prioritized:
    0. dependency manifests (anywhere, outside ignored dirs)
    1. top-level documentation (README, CONTRIBUTING, LICENSE, ...)
    2. configuration relevant to CI, containers and secrets
    3. a round-robin sample of source and test files across directories
Content is fetched from raw.githubusercontent.com at the pinned commit. That host does not
count against the REST API rate limit.
"""

import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from app.analyzers.file_classifier import FileCategory, classify, ignored_segment
from app.core.config import Settings
from app.services.repository_parser import RepoRef
from app.services.repository_tree import RepositoryTree, TreeEntry

logger = logging.getLogger(__name__)

# fmt: off
MANIFEST_FILENAMES: frozenset[str] = frozenset({
    "package.json", "pyproject.toml", "Pipfile", "setup.cfg", "pom.xml", "build.gradle",
    "build.gradle.kts", "Cargo.toml", "go.mod", "composer.json", "Gemfile",
})
_REQUIREMENTS_RE = re.compile(r"^requirements([-_.][\w.-]+)?\.(txt|in)$", re.IGNORECASE)
_DOC_STEMS = ("readme", "contributing", "license", "licence", "copying", "changelog",
              "code_of_conduct", "security", "changes", "history")
_SECURITY_CONFIG_NAMES = frozenset({
    ".gitignore", ".dockerignore", ".npmrc", ".pypirc", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml", "dependabot.yml", "renovate.json",
    ".pre-commit-config.yaml", "settings.py", "config.py", "application.properties",
    "application.yml", "application.yaml", "appsettings.json", "wp-config.php",
    "CODEOWNERS",
})
# fmt: on

MAX_MANIFESTS = 40
MAX_DOCS = 20
MAX_CONFIG = 40
BINARY_SNIFF_BYTES = 8192


def is_manifest(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in MANIFEST_FILENAMES:
        return True
    if _REQUIREMENTS_RE.match(name):
        return True
    parent = PurePosixPath(path).parent.name.lower()
    return parent == "requirements" and name.endswith(".txt")


def _is_top_level_doc(path: str) -> bool:
    p = PurePosixPath(path)
    in_root = len(p.parts) == 1 or (len(p.parts) == 2 and p.parts[0] in {".github", "docs"})
    return in_root and p.name.lower().split(".", 1)[0] in _DOC_STEMS


def _is_security_config(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name
    if name in _SECURITY_CONFIG_NAMES or name.startswith(("Dockerfile", ".env")):
        return True
    if name.endswith((".dockerfile", ".tf")):
        return True
    return len(p.parts) >= 3 and p.parts[0] == ".github" and p.parts[1] == "workflows"


@dataclass
class FetchStats:
    selected: int = 0
    fetched: int = 0
    bytes_fetched: int = 0
    skipped_binary: int = 0
    skipped_too_large: int = 0
    failed: int = 0
    budget_exhausted: bool = False
    rate_limited: bool = False


@dataclass
class FetchedContent:
    files: dict[str, str] = field(default_factory=dict)
    stats: FetchStats = field(default_factory=FetchStats)


def select_files(tree: RepositoryTree, settings: Settings) -> list[TreeEntry]:
    """Return the prioritized, bounded list of files whose content will be downloaded."""
    limit = settings.max_files_to_fetch
    candidates = [
        e
        for e in tree.files()
        if ignored_segment(e.path) is None and 0 < e.size <= settings.max_file_bytes
    ]
    candidates.sort(key=lambda e: e.path)

    chosen: list[TreeEntry] = []
    seen: set[str] = set()

    def take(entries: list[TreeEntry], cap: int) -> None:
        for e in entries[:cap]:
            if len(chosen) >= limit:
                return
            if e.path not in seen:
                seen.add(e.path)
                chosen.append(e)

    # Shallow manifests first, so the root project's manifest always wins.
    manifests = sorted(
        (e for e in candidates if is_manifest(e.path)), key=lambda e: (e.path.count("/"), e.path)
    )
    take(manifests, MAX_MANIFESTS)
    take([e for e in candidates if _is_top_level_doc(e.path)], MAX_DOCS)
    take(
        sorted(
            (e for e in candidates if _is_security_config(e.path)),
            key=lambda e: (e.path.count("/"), e.path),
        ),
        MAX_CONFIG,
    )

    # Round-robin over directories so a single huge folder cannot consume the whole budget.
    groups: dict[str, list[TreeEntry]] = defaultdict(list)
    for e in candidates:
        if e.path in seen:
            continue
        category = classify(e.path).category
        if category in (FileCategory.SOURCE, FileCategory.TEST):
            groups[str(PurePosixPath(e.path).parent)].append(e)
    queues = [groups[k] for k in sorted(groups)]
    index = 0
    while len(chosen) < limit and any(index < len(q) for q in queues):
        for q in queues:
            if index < len(q) and len(chosen) < limit:
                chosen.append(q[index])
        index += 1
    return chosen


def raw_url(settings: Settings, ref: RepoRef, sha: str, path: str) -> str:
    return (
        f"{settings.github_raw_url.rstrip('/')}/{ref.owner}/{ref.name}/{sha}/"
        f"{quote(path, safe='/')}"
    )


async def fetch_contents(
    http: httpx.AsyncClient,
    settings: Settings,
    ref: RepoRef,
    tree: RepositoryTree,
    entries: list[TreeEntry],
) -> FetchedContent:
    result = FetchedContent()
    result.stats.selected = len(entries)
    semaphore = asyncio.Semaphore(settings.fetch_concurrency)
    budget = {"remaining": settings.max_total_fetch_bytes}

    async def fetch_one(entry: TreeEntry) -> None:
        stats = result.stats
        if stats.rate_limited:
            return
        if entry.size > budget["remaining"]:
            stats.budget_exhausted = True
            return
        budget["remaining"] -= entry.size  # reserve up front, so parallel fetches can't overshoot
        async with semaphore:
            if stats.rate_limited:
                return
            try:
                data = await _download(
                    http,
                    raw_url(settings, ref, tree.commit_sha, entry.path),
                    settings.max_file_bytes,
                )
            except _TooLargeError:
                stats.skipped_too_large += 1
                return
            except _RateLimitError:
                stats.rate_limited = True
                return
            except (httpx.HTTPError, _FetchError) as exc:
                logger.info("Could not fetch %s: %s", entry.path, exc)
                stats.failed += 1
                return
        if b"\x00" in data[:BINARY_SNIFF_BYTES]:
            stats.skipped_binary += 1
            return
        result.files[entry.path] = data.decode("utf-8", errors="replace")
        stats.fetched += 1
        stats.bytes_fetched += len(data)

    await asyncio.gather(*(fetch_one(e) for e in entries))
    # Keep a stable order regardless of completion order.
    result.files = {e.path: result.files[e.path] for e in entries if e.path in result.files}
    return result


class _FetchError(Exception):
    pass


class _TooLargeError(_FetchError):
    pass


class _RateLimitError(_FetchError):
    pass


async def _download(http: httpx.AsyncClient, url: str, max_bytes: int) -> bytes:
    async with http.stream("GET", url) as response:
        if response.status_code == 429:
            raise _RateLimitError(url)
        if response.status_code != 200:
            raise _FetchError(f"HTTP {response.status_code}")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise _TooLargeError(url)
            chunks.append(chunk)
        return b"".join(chunks)
