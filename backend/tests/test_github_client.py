import httpx
import pytest

from app.core.config import Settings
from app.core.errors import (
    RateLimitedError,
    RepositoryNotFoundError,
    RepositoryUnavailableError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.services.github_client import GitHubClient, build_http_client
from app.services.repository_parser import RepoRef
from tests.fakes import FakeGitHub, json_response, repo_payload

pytestmark = pytest.mark.anyio
REF = RepoRef("octo", "demo")


def client_for(handler, settings: Settings) -> GitHubClient:
    http = build_http_client(settings, httpx.MockTransport(handler))
    return GitHubClient(http, settings)


async def test_fetches_and_maps_metadata(settings: Settings) -> None:
    fake = FakeGitHub()
    gh = client_for(fake.handle, settings)
    meta = await gh.get_repository(REF)
    assert meta.full_name == "octo/demo"
    assert meta.stars == 42 and meta.forks == 7 and meta.open_issues == 5
    assert meta.license_spdx == "MIT"
    assert meta.primary_language == "Python"
    assert meta.pushed_at is not None and meta.pushed_at.year == 2026
    assert gh.rate_limit.remaining == 59 and gh.rate_limit.limit == 60
    assert gh.api_calls == 1


async def test_sends_token_only_when_configured(settings: Settings) -> None:
    fake = FakeGitHub()
    await client_for(fake.handle, settings).get_repository(REF)
    assert "authorization" not in fake.requests[-1].headers

    authed = Settings(_env_file=None, github_token="ghp_test")
    gh = client_for(fake.handle, authed)
    await gh.get_repository(REF)
    assert fake.requests[-1].headers["authorization"] == "Bearer ghp_test"
    assert fake.requests[-1].headers["x-github-api-version"] == "2022-11-28"
    assert gh.rate_limit.authenticated is True


async def test_noassertion_license_is_treated_as_unknown(settings: Settings) -> None:
    fake = FakeGitHub(repo=repo_payload(license={"spdx_id": "NOASSERTION", "name": "Other"}))
    meta = await client_for(fake.handle, settings).get_repository(REF)
    assert meta.license_spdx is None


async def test_404_maps_to_not_found(settings: Settings) -> None:
    gh = client_for(lambda r: json_response({"message": "Not Found"}, 404), settings)
    with pytest.raises(RepositoryNotFoundError) as exc:
        await gh.get_repository(REF)
    assert exc.value.status_code == 404
    assert "private" in exc.value.message


async def test_private_repository_is_refused(settings: Settings) -> None:
    fake = FakeGitHub(repo=repo_payload(private=True))
    with pytest.raises(RepositoryNotFoundError):
        await client_for(fake.handle, settings).get_repository(REF)


async def test_primary_rate_limit(settings: Settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return json_response(
            {"message": "API rate limit exceeded for 1.2.3.4."},
            403,
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"},
        )

    with pytest.raises(RateLimitedError) as exc:
        await client_for(handler, settings).get_repository(REF)
    assert exc.value.reset_at is not None and exc.value.reset_at.year == 2030
    assert "GITHUB_TOKEN" in exc.value.message  # unauthenticated hint
    assert exc.value.status_code == 429


async def test_secondary_rate_limit_uses_retry_after(settings: Settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return json_response(
            {"message": "You have exceeded a secondary rate limit"},
            429,
            {"retry-after": "60", "x-ratelimit-remaining": "10"},
        )

    with pytest.raises(RateLimitedError) as exc:
        await client_for(handler, settings).get_repository(REF)
    assert exc.value.retry_after_seconds == 60


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (403, RepositoryUnavailableError),
        (451, RepositoryUnavailableError),
        (401, UpstreamError),
        (500, UpstreamError),
        (502, UpstreamError),
    ],
)
async def test_status_mapping(settings: Settings, status: int, error: type) -> None:
    gh = client_for(lambda r: json_response({"message": "nope"}, status), settings)
    with pytest.raises(error):
        await gh.get_repository(REF)


async def test_timeout_maps_to_upstream_timeout(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(UpstreamTimeoutError):
        await client_for(handler, settings).get_repository(REF)


async def test_network_failure_maps_to_upstream_error(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    with pytest.raises(UpstreamError):
        await client_for(handler, settings).get_repository(REF)


async def test_malformed_json_maps_to_upstream_error(settings: Settings) -> None:
    gh = client_for(lambda r: httpx.Response(200, content=b"<html>oops"), settings)
    with pytest.raises(UpstreamError):
        await gh.get_repository(REF)


async def test_incomplete_payload_maps_to_upstream_error(settings: Settings) -> None:
    gh = client_for(lambda r: json_response({"name": "demo"}), settings)
    with pytest.raises(UpstreamError):
        await gh.get_repository(REF)


async def test_renamed_repository_redirect_is_followed(settings: Settings) -> None:
    fake = FakeGitHub()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octo/old-name":
            return httpx.Response(
                301, headers={"location": "https://api.github.com/repos/octo/demo"}
            )
        return fake.handle(request)

    meta = await client_for(handler, settings).get_repository(RepoRef("octo", "old-name"))
    assert meta.name == "demo"
