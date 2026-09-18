from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeGitHub, json_response


def make_client(settings: Settings, fake: FakeGitHub | None = None) -> TestClient:
    fake = fake or FakeGitHub()
    return TestClient(create_app(settings, transport=fake.transport()))


def test_health(settings: Settings) -> None:
    with make_client(settings) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["ai_enabled"] is False


def test_repository_metadata_endpoint(settings: Settings) -> None:
    with make_client(settings) as client:
        response = client.get("/api/repositories/octo/demo")
    assert response.status_code == 200
    assert response.json()["full_name"] == "octo/demo"


def test_invalid_owner_returns_structured_422(settings: Settings) -> None:
    with make_client(settings) as client:
        response = client.get("/api/repositories/-bad-/demo")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_repository_url"


def test_not_found_returns_structured_404(settings: Settings) -> None:
    with make_client(settings) as client:
        response = client.get("/api/repositories/octo/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "repository_not_found"


def test_rate_limit_returns_429_with_reset(settings: Settings) -> None:
    fake = FakeGitHub(
        overrides={
            "/repos/": lambda r: json_response(
                {"message": "API rate limit exceeded"},
                403,
                {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"},
            )
        }
    )
    with make_client(settings, fake) as client:
        response = client.get("/api/repositories/octo/demo")
    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "rate_limited"
    assert error["details"]["reset_at"].startswith("2030-")


def test_large_responses_are_gzip_compressed(settings: Settings) -> None:
    with make_client(settings) as client:
        response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"
