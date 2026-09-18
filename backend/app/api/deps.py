from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.github_client import GitHubClient


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def get_github_client(
    http: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitHubClient:
    # One GitHubClient per request so per-request counters (API calls) stay isolated.
    return GitHubClient(http, settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
GitHubDep = Annotated[GitHubClient, Depends(get_github_client)]
HttpDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
