"""Thin async client for the parts of the GitHub REST API that RepoLens needs.

Every GitHub error condition gets translated into a RepoLensError subclass, so callers
never see raw httpx exceptions or status codes.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import APP_VERSION, Settings
from app.core.errors import (
    RateLimitedError,
    RepositoryNotFoundError,
    RepositoryUnavailableError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.schemas.repository import RateLimitInfo, RepositoryMetadata
from app.services.repository_parser import RepoRef

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"


def build_http_client(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Shared connection pool. Redirects are followed so renamed repositories resolve;
    httpx drops the Authorization header on any cross-origin redirect."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds, connect=10.0),
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": f"RepoLens/{APP_VERSION} (+https://github.com)"},
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        transport=transport,
    )


class GitHubClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._api = settings.github_api_url.rstrip("/")
        self._token = settings.github_token.get_secret_value() if settings.github_token else None
        self.rate_limit = RateLimitInfo(authenticated=self._token is not None)
        self.api_calls = 0

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def _api_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get_json(
        self, path: str, *, params: dict[str, str] | None = None, context: str = "repository"
    ) -> Any:
        url = f"{self._api}{path}"
        self.api_calls += 1
        try:
            response = await self._http.get(url, headers=self._api_headers(), params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError(
                "GitHub did not respond in time. Try again shortly."
            ) from exc
        except httpx.TransportError as exc:
            logger.warning("GitHub transport error for %s: %s", path, exc)
            raise UpstreamError(
                "Could not reach GitHub. Check your network and try again."
            ) from exc

        self._record_rate_limit(response)
        self._raise_for_status(response, context)
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("GitHub returned a malformed response.") from exc

    def _record_rate_limit(self, response: httpx.Response) -> None:
        h = response.headers
        try:
            if "x-ratelimit-limit" in h:
                self.rate_limit.limit = int(h["x-ratelimit-limit"])
            if "x-ratelimit-remaining" in h:
                self.rate_limit.remaining = int(h["x-ratelimit-remaining"])
            if "x-ratelimit-reset" in h:
                self.rate_limit.reset_at = datetime.fromtimestamp(int(h["x-ratelimit-reset"]), UTC)
        except ValueError:
            logger.debug("Ignoring malformed rate-limit headers")

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        status = response.status_code
        if status < 400:
            return
        message = _error_message(response)

        if status in (403, 429) and _is_rate_limited(response, message):
            retry_after = response.headers.get("retry-after")
            hint = "" if self.authenticated else " Configure GITHUB_TOKEN to raise the limit."
            raise RateLimitedError(
                f"GitHub API rate limit exceeded.{hint}",
                reset_at=self.rate_limit.reset_at,
                retry_after_seconds=int(retry_after)
                if retry_after and retry_after.isdigit()
                else None,
            )
        if status == 404:
            raise RepositoryNotFoundError(
                f"The {context} was not found. It may be private, deleted or misspelled."
            )
        if status == 401:
            logger.error("GitHub rejected the configured token (401)")
            raise UpstreamError("GitHub rejected the server's credentials.")
        if status == 451:
            raise RepositoryUnavailableError(
                "This repository is unavailable for legal reasons (e.g. a DMCA takedown)."
            )
        if status == 403:
            raise RepositoryUnavailableError(f"GitHub denied access to this {context}.")
        if status == 409:
            raise RepositoryUnavailableError("The repository is empty.")
        logger.warning("GitHub returned %s: %s", status, message[:200])
        raise UpstreamError(f"GitHub returned an unexpected error (HTTP {status}).")

    async def get_repository(self, ref: RepoRef) -> RepositoryMetadata:
        data = await self._get_json(f"/repos/{ref.owner}/{ref.name}")
        if not isinstance(data, dict):
            raise UpstreamError("GitHub returned a malformed repository response.")
        if data.get("private"):
            # Only possible with a token that can see private repos; RepoLens analyzes public code.
            raise RepositoryNotFoundError("Only public repositories can be analyzed.")
        return parse_repository_metadata(data)


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    return str(body.get("message", "")) if isinstance(body, dict) else ""


def _is_rate_limited(response: httpx.Response, message: str) -> bool:
    return (
        response.status_code == 429
        or response.headers.get("x-ratelimit-remaining") == "0"
        or "rate limit" in message.lower()
    )


def parse_repository_metadata(data: dict[str, Any]) -> RepositoryMetadata:
    try:
        owner = data["owner"]
        license_info = data.get("license") or {}
        spdx = license_info.get("spdx_id")
        return RepositoryMetadata(
            owner=owner["login"],
            name=data["name"],
            full_name=data["full_name"],
            html_url=data["html_url"],
            description=data.get("description"),
            homepage=data.get("homepage") or None,
            default_branch=data["default_branch"],
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            watchers=data.get("subscribers_count", data.get("watchers_count", 0)),
            open_issues=data.get("open_issues_count", 0),
            primary_language=data.get("language"),
            license_spdx=spdx if spdx and spdx != "NOASSERTION" else None,
            license_name=license_info.get("name"),
            topics=list(data.get("topics") or []),
            size_kb=data.get("size", 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            pushed_at=data.get("pushed_at"),
            archived=bool(data.get("archived")),
            disabled=bool(data.get("disabled")),
            is_fork=bool(data.get("fork")),
            is_template=bool(data.get("is_template")),
            owner_type=owner.get("type"),
            owner_avatar_url=owner.get("avatar_url"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("GitHub returned an incomplete repository response.") from exc
