import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import UpstreamError
from app.core.rate_limit import SlidingWindowLimiter
from app.main import create_app
from app.services.github_client import GitHubClient, build_http_client
from app.services.repository_parser import RepoRef
from tests.fakes import FakeGitHub
from tests.test_pipeline import REPO_FILES


def make(fake: FakeGitHub | None = None, **overrides: object) -> TestClient:
    base: dict = {"github_token": None, "rate_limit_per_minute": 0}
    base.update(overrides)
    settings = Settings(_env_file=None, **base)
    fake = fake or FakeGitHub(files=REPO_FILES)
    return TestClient(create_app(settings, transport=fake.transport(), ai_provider=None))


def test_sliding_window_limiter() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 60, clock=lambda: now[0])
    assert limiter.check("a") is None and limiter.check("a") is None
    assert limiter.check("a") == 60
    assert limiter.check("b") is None  # independent clients
    now[0] = 30
    assert limiter.check("a") == 30
    now[0] = 61
    assert limiter.check("a") is None
    assert SlidingWindowLimiter(0, 60).check("x") is None  # disabled


def test_analysis_rate_limit_returns_429_with_retry_after() -> None:
    with make(rate_limit_per_minute=2) as client:
        codes = [
            client.post("/api/analyze", json={"repository_url": "octo/demo"}).status_code
            for _ in range(3)
        ]
        streamed = client.post("/api/analyze/stream", json={"repository_url": "octo/demo"})
    assert codes == [200, 200, 429]
    assert streamed.status_code == 429  # rejected before streaming starts
    assert streamed.json()["error"]["code"] == "too_many_requests"
    assert int(streamed.headers["retry-after"]) > 0


def test_forwarded_for_is_only_trusted_when_configured() -> None:
    def two_requests(client: TestClient) -> list[int]:
        return [
            client.post(
                "/api/analyze",
                json={"repository_url": "octo/demo"},
                headers={"X-Forwarded-For": ip},
            ).status_code
            for ip in ("1.1.1.1", "2.2.2.2")
        ]

    with make(rate_limit_per_minute=1) as client:
        assert two_requests(client) == [200, 429]  # spoofed header ignored: same client
    with make(rate_limit_per_minute=1, trust_proxy_headers=True) as client:
        assert two_requests(client) == [200, 200]  # behind a trusted proxy: distinct clients


def test_request_size_limit_and_security_headers() -> None:
    with make(max_request_bytes=100) as client:
        big = client.post(
            "/api/analyze",
            content=b'{"repository_url": "' + b"a" * 200 + b'"}',
            headers={"content-type": "application/json"},
        )
        ok = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert big.status_code == 413 and big.json()["error"]["code"] == "request_too_large"
    assert ok.headers["x-request-id"] == "abc123"
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert ok.headers["x-frame-options"] == "DENY"


def test_docs_can_be_disabled() -> None:
    with make(enable_docs=False) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


@pytest.mark.anyio
async def test_egress_allowlist_blocks_unexpected_hosts() -> None:
    settings = Settings(_env_file=None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return httpx.Response(200, json={})

    async with build_http_client(settings, httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamError, match="unexpected host"):
            await GitHubClient(http, settings).get_repository(RepoRef("octo", "demo"))


def test_concurrent_identical_analyses_are_coalesced() -> None:
    fake = FakeGitHub(files=REPO_FILES)
    gate = asyncio.Event()
    original = fake.handle

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octo/demo":
            await gate.wait()
        return original(request)

    settings = Settings(_env_file=None, github_token=None, rate_limit_per_minute=0)
    app = create_app(settings, transport=httpx.MockTransport(slow_handler), ai_provider=None)

    async def scenario() -> list[int]:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                tasks = [
                    asyncio.create_task(
                        client.post("/api/analyze", json={"repository_url": "octo/demo"})
                    )
                    for _ in range(3)
                ]
                await asyncio.sleep(0.2)
                gate.set()
                responses = await asyncio.gather(*tasks)
        return [r.status_code for r in responses]

    assert asyncio.run(scenario()) == [200, 200, 200]
    metadata_calls = [r for r in fake.requests if r.url.path == "/repos/octo/demo"]
    assert len(metadata_calls) == 1  # one analysis served all three requests


def test_analysis_timeout_returns_504() -> None:
    async def hanging(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    settings = Settings(
        _env_file=None, github_token=None, rate_limit_per_minute=0, analysis_timeout_seconds=0.2
    )
    app = create_app(settings, transport=httpx.MockTransport(hanging), ai_provider=None)
    with TestClient(app) as client:
        response = client.post("/api/analyze", json={"repository_url": "octo/demo"})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "analysis_timeout"


def test_proxy_secret_controls_client_ip_trust() -> None:
    def hit(client: TestClient, ip: str, secret: str | None) -> int:
        headers = {"X-RepoLens-Client-IP": ip}
        if secret:
            headers["X-RepoLens-Proxy-Secret"] = secret
        return client.post(
            "/api/analyze", json={"repository_url": "octo/demo"}, headers=headers
        ).status_code

    with make(rate_limit_per_minute=1, proxy_shared_secret="s3cret-value") as client:
        assert hit(client, "1.1.1.1", "s3cret-value") == 200
        assert hit(client, "2.2.2.2", "s3cret-value") == 200  # distinct real clients
        assert hit(client, "1.1.1.1", "s3cret-value") == 429
        # Without (or with a wrong) secret the header is ignored: TCP peer is the identity.
        assert hit(client, "3.3.3.3", "wrong") == 200
        assert hit(client, "4.4.4.4", None) == 429
        assert hit(client, "not-an-ip", "s3cret-value") == 429  # invalid IP falls back
