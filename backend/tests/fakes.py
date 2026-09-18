"""An in-process fake of the GitHub REST API + raw content host, built on httpx.MockTransport.

It serves real HTTP responses so the production client code (header handling, status mapping,
JSON parsing, redirects) runs unmodified in tests.
"""

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

Handler = Callable[[httpx.Request], httpx.Response]


def repo_payload(owner: str = "octo", name: str = "demo", **overrides: object) -> dict:
    data: dict = {
        "name": name,
        "full_name": f"{owner}/{name}",
        "html_url": f"https://github.com/{owner}/{name}",
        "private": False,
        "description": "A demo repository",
        "homepage": "",
        "default_branch": "main",
        "stargazers_count": 42,
        "forks_count": 7,
        "subscribers_count": 3,
        "open_issues_count": 5,
        "language": "Python",
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "topics": ["demo"],
        "size": 120,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2026-09-01T00:00:00Z",
        "pushed_at": "2026-09-01T00:00:00Z",
        "archived": False,
        "disabled": False,
        "fork": False,
        "is_template": False,
        "owner": {"login": owner, "type": "Organization", "avatar_url": "https://x/avatar.png"},
    }
    data.update(overrides)
    return data


@dataclass
class FakeGitHub:
    owner: str = "octo"
    name: str = "demo"
    repo: dict | None = None
    files: dict[str, str | bytes] = field(default_factory=dict)
    symlinks: dict[str, str] = field(default_factory=dict)  # link path -> target text
    languages: dict[str, int] | None = None
    tree_truncated: bool = False
    commit_sha: str = "abc123"
    overrides: dict[str, Handler] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = repo_payload(self.owner, self.name)

    # --- helpers -----------------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def tree_entries(self) -> list[dict]:
        entries: dict[str, dict] = {}
        for path, content in self.files.items():
            parts = path.split("/")
            for i in range(1, len(parts)):
                d = "/".join(parts[:i])
                entries.setdefault(d, {"path": d, "type": "tree", "mode": "040000", "sha": "t"})
            raw = content.encode() if isinstance(content, str) else content
            entries[path] = {
                "path": path,
                "type": "blob",
                "mode": "100644",
                "sha": f"sha-{path}",
                "size": len(raw),
            }
        for path, target in self.symlinks.items():
            entries[path] = {
                "path": path,
                "type": "blob",
                "mode": "120000",
                "sha": f"sha-{path}",
                "size": len(target),
            }
        return sorted(entries.values(), key=lambda e: e["path"])

    # --- routing -----------------------------------------------------------
    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        for prefix, handler in self.overrides.items():
            if path.startswith(prefix):
                return handler(request)

        base = f"/repos/{self.owner}/{self.name}"
        if request.url.host == "api.github.com":
            if path == base:
                return _json(self.repo)
            if path == f"{base}/languages":
                return _json(self.languages or {})
            if path == f"{base}/commits/{self.repo['default_branch']}":
                return _json(
                    {
                        "sha": self.commit_sha,
                        "commit": {"committer": {"date": "2026-09-01T00:00:00Z"}},
                    }
                )
            if path.startswith(f"{base}/git/trees/"):
                return _json(
                    {
                        "sha": self.commit_sha,
                        "tree": self.tree_entries(),
                        "truncated": self.tree_truncated,
                    }
                )
            if path == f"{base}/commits":
                return _json([])
            return _json({"message": "Not Found"}, 404)

        if request.url.host == "raw.githubusercontent.com":
            prefix = f"/{self.owner}/{self.name}/{self.commit_sha}/"
            if path.startswith(prefix):
                file_path = httpx.URL(request.url).path[len(prefix) :]
                content = self.files.get(file_path, self.symlinks.get(file_path))
                if content is not None:
                    body = content.encode() if isinstance(content, str) else content
                    return httpx.Response(200, content=body)
            return httpx.Response(404, text="404: Not Found")
        return httpx.Response(599, text="unexpected host")


def _json(data: object, status: int = 200, headers: dict | None = None) -> httpx.Response:
    base_headers = {
        "x-ratelimit-limit": "60",
        "x-ratelimit-remaining": "59",
        "x-ratelimit-reset": "1900000000",
    }
    base_headers.update(headers or {})
    return httpx.Response(status, content=json.dumps(data), headers=base_headers)


def json_response(data: object, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return _json(data, status, headers)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()
