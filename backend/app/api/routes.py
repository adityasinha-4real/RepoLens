from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import GitHubDep, SettingsDep
from app.core.config import APP_VERSION
from app.schemas.repository import RepositoryMetadata
from app.services.repository_parser import parse_repository_url

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str
    version: str
    ai_enabled: bool


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", version=APP_VERSION, ai_enabled=bool(settings.ai_provider))


@router.get("/repositories/{owner}/{name}", response_model=RepositoryMetadata)
async def repository_metadata(owner: str, name: str, github: GitHubDep) -> RepositoryMetadata:
    ref = parse_repository_url(f"{owner}/{name}")
    return await github.get_repository(ref)
