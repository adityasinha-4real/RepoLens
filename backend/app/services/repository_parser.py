"""Parse and validate user-supplied GitHub repository references.

Accepted forms:
    https://github.com/owner/repo
    http://www.github.com/owner/repo.git
    github.com/owner/repo/tree/main/src      (extra path segments are ignored)
    git@github.com:owner/repo.git
    owner/repo
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import InvalidRepositoryURLError

MAX_INPUT_LENGTH = 512

# GitHub rules: owners are 1-39 alphanumerics or single hyphens, not starting or ending with one.
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
# Repository names: 1-100 chars of letters, digits, '.', '-', '_'.
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SSH_RE = re.compile(r"^git@github\.com:(?P<path>[^\s]+)$", re.IGNORECASE)
_ALLOWED_HOSTS = {"github.com", "www.github.com"}
# First path segments on github.com that are site pages, not users or organizations.
_RESERVED_OWNERS = {
    "about",
    "apps",
    "collections",
    "contact",
    "customer-stories",
    "enterprise",
    "explore",
    "features",
    "issues",
    "login",
    "marketplace",
    "new",
    "notifications",
    "orgs",
    "pricing",
    "pulls",
    "search",
    "settings",
    "sponsors",
    "topics",
    "trending",
    "join",
    "site",
}


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.full_name}"


def parse_repository_url(raw: str) -> RepoRef:
    """Return owner/name for a GitHub repository reference, or raise InvalidRepositoryURLError."""
    if not isinstance(raw, str):
        raise InvalidRepositoryURLError("Repository URL must be a string.")
    value = raw.strip()
    if not value:
        raise InvalidRepositoryURLError("Enter a GitHub repository URL.")
    if len(value) > MAX_INPUT_LENGTH:
        raise InvalidRepositoryURLError("Repository URL is too long.")
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise InvalidRepositoryURLError("Repository URL must not contain whitespace.")

    ssh = _SSH_RE.match(value)
    if ssh:
        path = ssh.group("path")
    elif "://" in value or value.lower().startswith(("github.com/", "www.github.com/")):
        if "://" not in value:
            value = "https://" + value
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"}:
            raise InvalidRepositoryURLError("Only http(s) GitHub URLs are supported.")
        host = (parts.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            raise InvalidRepositoryURLError("Only github.com repositories are supported.")
        if parts.username or parts.password or parts.port:
            raise InvalidRepositoryURLError(
                "Repository URL must not contain credentials or a port."
            )
        path = parts.path
    else:
        path = value  # shorthand "owner/repo"

    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        raise InvalidRepositoryURLError(
            "URL must point to a repository, e.g. https://github.com/owner/repository."
        )
    owner, name = segments[0], segments[1]
    if name.lower().endswith(".git"):
        name = name[:-4]

    if owner.lower() in _RESERVED_OWNERS or not _OWNER_RE.match(owner):
        raise InvalidRepositoryURLError(f"'{owner[:50]}' is not a valid GitHub owner name.")
    if not _REPO_RE.match(name) or name in {".", ".."}:
        raise InvalidRepositoryURLError(f"'{name[:100]}' is not a valid GitHub repository name.")
    return RepoRef(owner=owner, name=name)
