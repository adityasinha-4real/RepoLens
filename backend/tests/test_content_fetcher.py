import httpx
import pytest

from app.core.config import Settings
from app.services.content_fetcher import fetch_contents, is_manifest, select_files
from app.services.github_client import GitHubClient, build_http_client
from app.services.repository_parser import RepoRef
from app.services.repository_tree import RepositoryTree, TreeEntry
from app.services.snapshot import collect_snapshot
from tests.fakes import FakeGitHub

pytestmark = pytest.mark.anyio
REF = RepoRef("octo", "demo")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("package.json", True),
        ("apps/web/package.json", True),
        ("requirements.txt", True),
        ("requirements-dev.txt", True),
        ("requirements/prod.txt", True),
        ("pyproject.toml", True),
        ("build.gradle.kts", True),
        ("go.mod", True),
        ("package-lock.json", False),
        ("src/requirements_parser.py", False),
    ],
)
def test_is_manifest(path: str, expected: bool) -> None:
    assert is_manifest(path) is expected


def test_selection_priorities_and_limits() -> None:
    files = {f"src/mod{i}/f{j}.py": 100 for i in range(5) for j in range(20)}
    files |= {
        "package.json": 50,
        "README.md": 50,
        ".gitignore": 10,
        ".github/workflows/ci.yml": 30,
        "big.py": 10_000_000,
        "node_modules/a/package.json": 10,
        "empty.py": 0,
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", s) for p, s in files.items()])
    settings = Settings(_env_file=None, max_files_to_fetch=14, max_file_bytes=1_000)

    chosen = [e.path for e in select_files(tree, settings)]
    assert chosen[:4] == ["package.json", "README.md", ".gitignore", ".github/workflows/ci.yml"]
    assert len(chosen) == 14
    assert "big.py" not in chosen and "empty.py" not in chosen
    assert "node_modules/a/package.json" not in chosen
    # the sample is spread round-robin across the five source directories
    dirs = {p.split("/")[1] for p in chosen[4:]}
    assert dirs == {f"mod{i}" for i in range(5)}


async def test_fetch_enforces_size_binary_and_failure_handling() -> None:
    fake = FakeGitHub(
        files={
            "ok.py": "print(1)\n",
            "lies.py": "x" * 5_000,  # tree says small, body is large -> streaming cap kicks in
            "blob.dat.py": b"\x00\x01binary",
        }
    )
    settings = Settings(_env_file=None, max_file_bytes=1_000)
    tree = RepositoryTree(
        fake.commit_sha,
        [
            TreeEntry("ok.py", "file", 9),
            TreeEntry("lies.py", "file", 10),
            TreeEntry("blob.dat.py", "file", 9),
            TreeEntry("missing.py", "file", 5),
        ],
    )
    async with build_http_client(settings, fake.transport()) as http:
        result = await fetch_contents(http, settings, REF, tree, tree.files())
    assert result.files == {"ok.py": "print(1)\n"}
    s = result.stats
    assert (s.fetched, s.skipped_too_large, s.skipped_binary, s.failed) == (1, 1, 1, 1)
    raw_paths = [r.url.path for r in fake.requests]
    assert "/octo/demo/abc123/ok.py" in raw_paths  # pinned to the commit SHA


async def test_fetch_stops_on_raw_rate_limit() -> None:
    settings = Settings(_env_file=None, fetch_concurrency=1)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429)

    tree = RepositoryTree("sha", [TreeEntry(f"f{i}.py", "file", 5) for i in range(10)])
    async with build_http_client(settings, httpx.MockTransport(handler)) as http:
        result = await fetch_contents(http, settings, REF, tree, tree.files())
    assert result.stats.rate_limited
    assert len(calls) == 1


async def test_fetch_respects_total_byte_budget() -> None:
    fake = FakeGitHub(files={f"f{i}.py": "x" * 100 for i in range(10)})
    settings = Settings(_env_file=None, max_total_fetch_bytes=350)
    tree = RepositoryTree(fake.commit_sha, [TreeEntry(f"f{i}.py", "file", 100) for i in range(10)])
    async with build_http_client(settings, fake.transport()) as http:
        result = await fetch_contents(http, settings, REF, tree, tree.files())
    assert result.stats.fetched == 3
    assert result.stats.budget_exhausted


async def test_path_is_url_encoded() -> None:
    fake = FakeGitHub(files={"docs/a b#c?.md": "hello"})
    settings = Settings(_env_file=None)
    tree = RepositoryTree(fake.commit_sha, [TreeEntry("docs/a b#c?.md", "file", 5)])
    async with build_http_client(settings, fake.transport()) as http:
        result = await fetch_contents(http, settings, REF, tree, tree.files())
    assert result.files == {"docs/a b#c?.md": "hello"}


async def test_collect_snapshot_end_to_end(settings: Settings) -> None:
    fake = FakeGitHub(
        files={
            "README.md": "# Demo\n",
            "src/app.py": "print('x')\n",
            "requirements.txt": "fastapi==0.115\n",
        },
        languages={"Python": 11},
    )
    stages: list[str] = []

    async def progress(stage: str, _: str) -> None:
        stages.append(stage)

    async with build_http_client(settings, fake.transport()) as http:
        snap = await collect_snapshot(GitHubClient(http, settings), http, settings, REF, progress)
    assert stages == ["metadata", "tree", "contents"]
    assert set(snap.contents) == {"README.md", "src/app.py", "requirements.txt"}
    assert snap.github_languages == {"Python": 11}
    assert snap.api_calls == 4  # repo, commit, tree, languages - raw fetches are free
    assert snap.tree.commit_sha == "abc123"
