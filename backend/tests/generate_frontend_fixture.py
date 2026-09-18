"""Write a real report produced by the full pipeline (against the in-process fake GitHub) to
frontend/tests/fixtures/report.json, for frontend rendering tests.

    python -m tests.generate_frontend_fixture
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeGitHub
from tests.test_pipeline import REPO_FILES

OUT = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "report.json"


def main() -> None:
    fake = FakeGitHub(files=REPO_FILES, languages={"Python": 900, "Dockerfile": 40})
    settings = Settings(_env_file=None, github_token=None, rate_limit_per_minute=0)
    with TestClient(create_app(settings, transport=fake.transport())) as client:
        response = client.post("/api/analyze", json={"repository_url": "octo/demo"})
    response.raise_for_status()
    report = response.json()
    # Stable values so the fixture does not churn on every regeneration.
    report["analysis"]["analyzed_at"] = datetime(2026, 9, 18, tzinfo=UTC).isoformat()
    report["analysis"]["duration_ms"] = 1234
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
