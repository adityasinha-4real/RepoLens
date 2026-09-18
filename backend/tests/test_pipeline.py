"""Integration tests: the complete analysis pipeline through the HTTP API.

The fake GitHub serves a small but realistic repository. Every layer runs for real: URL
parsing, the GitHub client, file selection, raw downloads, all analyzers, report assembly,
schema validation and JSON serialization.
"""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.analyzers.report_generator import build_health_report
from app.core.config import Settings
from app.main import create_app
from app.schemas.report import AnalysisReport
from tests.fakes import FakeGitHub, json_response, repo_payload

REPO_FILES: dict[str, str] = {
    "README.md": "# Demo\n\nA demo service.\n\n## Installation\n\n```bash\npip install demo\n"
    "```\n\n## Usage\n\nRun `demo`.\n\nSee [docs](docs/index.md).\n",
    "LICENSE": "MIT License",
    "CONTRIBUTING.md": "Open a PR.",
    ".gitignore": "__pycache__/\n.env\n",
    "pyproject.toml": '[project]\nname = "demo"\ndependencies = ["fastapi>=0.115", '
    '"httpx==0.27.0"]\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n'
    '[project.scripts]\ndemo = "demo.cli:main"\n[tool.ruff]\nline-length = 100\n',
    "demo/__init__.py": "",
    "demo/api/__init__.py": "",
    "demo/api/routes.py": "from demo.services.users import get_user\n\n\ndef list_users():\n"
    "    # TODO: paginate\n    return [get_user(1)]\n",
    "demo/services/__init__.py": "",
    "demo/services/users.py": 'import os\n\nDB = os.getenv("DATABASE_URL")\n\n\ndef get_user(i):\n'
    '    """Return a user."""\n    return {"id": i}\n',
    "demo/cli.py": "from demo.api.routes import list_users\n\n\ndef main():\n"
    "    print(list_users())\n\n\nif __name__ == '__main__':\n    main()\n",
    "tests/test_users.py": "from demo.services.users import get_user\n\n\ndef test_get_user():\n"
    "    assert get_user(1)['id'] == 1\n",
    "docs/index.md": "# Docs\n",
    ".github/workflows/ci.yml": "on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
    "    steps:\n      - uses: actions/checkout@v4\n",
    "Dockerfile": 'FROM python\nCOPY . .\nCMD ["demo"]\n',
    "node_modules/leftpad/index.js": "module.exports = 1\n",
}


def make_client(fake: FakeGitHub, **overrides: object) -> TestClient:
    settings = Settings(_env_file=None, github_token=None, rate_limit_per_minute=0, **overrides)
    return TestClient(create_app(settings, transport=fake.transport()))


def test_full_pipeline_via_api() -> None:
    fake = FakeGitHub(files=REPO_FILES, languages={"Python": 900, "Dockerfile": 40})
    with make_client(fake) as client:
        response = client.post(
            "/api/analyze", json={"repository_url": "https://github.com/octo/demo"}
        )
    assert response.status_code == 200, response.text
    report = AnalysisReport.model_validate(response.json())  # schema round-trip

    assert report.repository.full_name == "octo/demo"
    assert report.analysis.commit_sha == "abc123"
    assert report.analysis.github_api_calls == 4
    assert not report.analysis.partial

    s = report.structure
    assert s.ignored_files == 1 and s.ignored_directories[0].path == "node_modules"
    assert report.languages.github_breakdown[0].language == "Python"
    assert {d.name for d in report.dependencies.dependencies} == {"fastapi", "httpx", "pytest"}
    assert report.quality.test_files == 1
    assert report.quality.marker_counts["TODO"] == 1
    assert "Ruff" in report.quality.tooling.linters
    assert report.quality.tooling.ci == ["GitHub Actions"]
    assert report.documentation.readme is not None
    assert report.documentation.readme.broken_relative_links == []
    assert "DATABASE_URL" in report.security.env_variables
    assert any(f.rule == "docker.unpinned-base-image" for f in report.security.findings)

    arch = report.architecture
    assert "FastAPI" in {f.name for f in arch.frameworks}
    edges = {(e.source, e.target) for e in arch.edges}
    assert ("demo/api", "demo/services") in edges
    assert ("tests", "demo/services") in edges
    assert any(e.kind == "CLI command" for e in arch.entry_points)

    dims = {d.key: d for d in report.health.dimensions}
    assert set(dims) == {
        "documentation",
        "organization",
        "tests",
        "dependencies",
        "activity",
        "security",
        "structure",
    }
    assert all(0 <= (d.score or 0) <= 100 for d in dims.values())
    assert report.health.overall is not None
    assert dims["structure"].checks[0].passed is False  # node_modules committed


def test_stream_emits_progress_then_result() -> None:
    fake = FakeGitHub(files=REPO_FILES)
    with (
        make_client(fake) as client,
        client.stream(
            "POST", "/api/analyze/stream", json={"repository_url": "octo/demo"}
        ) as response,
    ):
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.iter_lines() if line]
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["validate", "metadata", "tree", "contents", "analyze"]
    assert events[-1]["type"] == "result"
    AnalysisReport.model_validate(events[-1]["report"])


def test_stream_reports_errors_as_events() -> None:
    fake = FakeGitHub()
    with (
        make_client(fake) as client,
        client.stream(
            "POST", "/api/analyze/stream", json={"repository_url": "octo/missing"}
        ) as response,
    ):
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert events[-1] == {
        "type": "error",
        "error": {
            "code": "repository_not_found",
            "message": "The repository was not found. It may be private, deleted or misspelled.",
            "details": {},
            "status": 404,
        },
    }


def test_invalid_url_and_request_validation() -> None:
    with make_client(FakeGitHub()) as client:
        bad_url = client.post("/api/analyze", json={"repository_url": "https://gitlab.com/a/b"})
        missing = client.post("/api/analyze", json={})
        too_long = client.post("/api/analyze", json={"repository_url": "a" * 600})
    assert bad_url.status_code == 422
    assert bad_url.json()["error"]["code"] == "invalid_repository_url"
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "invalid_request"
    assert too_long.status_code == 422


def test_rate_limit_during_analysis_returns_429() -> None:
    fake = FakeGitHub(files=REPO_FILES)
    fake.overrides["/repos/octo/demo/git/trees"] = lambda r: json_response(
        {"message": "API rate limit exceeded"},
        403,
        {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"},
    )
    with make_client(fake) as client:
        response = client.post("/api/analyze", json={"repository_url": "octo/demo"})
    assert response.status_code == 429
    assert response.json()["error"]["details"]["reset_at"].startswith("2030")


def test_limits_mark_report_partial() -> None:
    fake = FakeGitHub(files=REPO_FILES, tree_truncated=True)
    with make_client(fake, max_total_fetch_bytes=200) as client:
        report = client.post("/api/analyze", json={"repository_url": "octo/demo"}).json()
    assert report["analysis"]["partial"] is True
    assert report["analysis"]["fetch"]["budget_exhausted"] is True
    assert any("truncated" in n for n in report["analysis"]["notes"])


def test_archived_empty_repository_health() -> None:
    fake = FakeGitHub(
        files={"notes.txt": "hello"},
        repo=repo_payload(archived=True, pushed_at="2019-01-01T00:00:00Z", license=None),
    )
    with make_client(fake) as client:
        report = AnalysisReport.model_validate(
            client.post("/api/analyze", json={"repository_url": "octo/demo"}).json()
        )
    dims = {d.key: d for d in report.health.dimensions}
    activity = {c.id: c for c in dims["activity"].checks}
    assert activity["activity.recent_push"].points == 0
    assert activity["activity.not_archived"].passed is False
    assert dims["tests"].applicable is False  # no source files: not scored
    assert dims["dependencies"].applicable is False
    assert report.health.overall is not None


def test_health_activity_uses_injected_clock() -> None:
    fake_report = None
    fake = FakeGitHub(files=REPO_FILES)
    with make_client(fake) as client:
        fake_report = AnalysisReport.model_validate(
            client.post("/api/analyze", json={"repository_url": "octo/demo"}).json()
        )
    later = datetime(2027, 10, 1, tzinfo=UTC)
    health = build_health_report(
        metadata=fake_report.repository,
        head_commit_date=fake_report.analysis.head_commit_date,
        structure=fake_report.structure,
        quality=fake_report.quality,
        dependencies=fake_report.dependencies,
        documentation=fake_report.documentation,
        security=fake_report.security,
        architecture=fake_report.architecture,
        now=later,
    )
    activity = next(d for d in health.dimensions if d.key == "activity")
    push = next(c for c in activity.checks if c.id == "activity.recent_push")
    assert push.points == 0 and "395 days ago" in push.detail
