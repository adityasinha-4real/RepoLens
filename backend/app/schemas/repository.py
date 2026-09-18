from datetime import datetime

from pydantic import BaseModel


class RepositoryMetadata(BaseModel):
    """Repository facts exactly as reported by the GitHub REST API."""

    owner: str
    name: str
    full_name: str
    html_url: str
    description: str | None = None
    homepage: str | None = None
    default_branch: str
    stars: int
    forks: int
    watchers: int
    open_issues: int  # GitHub counts open issues *and* open pull requests here
    primary_language: str | None = None
    license_spdx: str | None = None
    license_name: str | None = None
    topics: list[str] = []
    size_kb: int  # GitHub's approximate repository size, including git history
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    archived: bool = False
    disabled: bool = False
    is_fork: bool = False
    is_template: bool = False
    owner_type: str | None = None  # "User" or "Organization"
    owner_avatar_url: str | None = None


class RateLimitInfo(BaseModel):
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None
    authenticated: bool = False
