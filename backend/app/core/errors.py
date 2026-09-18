"""Domain errors. Each maps to a stable machine-readable code and an HTTP status."""

from datetime import datetime


class RepoLensError(Exception):
    code = "internal_error"
    status_code = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRepositoryURLError(RepoLensError):
    code = "invalid_repository_url"
    status_code = 422


class RepositoryNotFoundError(RepoLensError):
    """404 from GitHub. Private repositories are indistinguishable from missing ones."""

    code = "repository_not_found"
    status_code = 404


class RepositoryUnavailableError(RepoLensError):
    """Repository exists but cannot be read (blocked, DMCA takedown, access denied, empty)."""

    code = "repository_unavailable"
    status_code = 403


class RepositoryTooLargeError(RepoLensError):
    code = "repository_too_large"
    status_code = 413


class RateLimitedError(RepoLensError):
    code = "rate_limited"
    status_code = 429

    def __init__(
        self,
        message: str,
        *,
        reset_at: datetime | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        details: dict = {}
        if reset_at is not None:
            details["reset_at"] = reset_at.isoformat()
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(message, details=details)
        self.reset_at = reset_at
        self.retry_after_seconds = retry_after_seconds


class UpstreamError(RepoLensError):
    """GitHub returned an unexpected error or malformed data."""

    code = "upstream_error"
    status_code = 502


class UpstreamTimeoutError(RepoLensError):
    code = "upstream_timeout"
    status_code = 504


class AIUnavailableError(RepoLensError):
    code = "ai_unavailable"
    status_code = 503


class TooManyRequestsError(RepoLensError):
    """This RepoLens instance's own per-client limit (distinct from GitHub's rate limit)."""

    code = "too_many_requests"
    status_code = 429

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})


class ServerBusyError(RepoLensError):
    code = "server_busy"
    status_code = 503


class AnalysisTimeoutError(RepoLensError):
    code = "analysis_timeout"
    status_code = 504


class RequestTooLargeError(RepoLensError):
    code = "request_too_large"
    status_code = 413
