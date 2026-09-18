import pytest

from app.core.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: tests must not pick up a developer's local .env
    return Settings(_env_file=None, github_token=None, rate_limit_per_minute=0)
