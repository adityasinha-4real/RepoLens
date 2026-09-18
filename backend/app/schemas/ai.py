from datetime import datetime

from pydantic import BaseModel, Field


class KeyModule(BaseModel):
    path: str = Field(max_length=300)
    description: str = Field(max_length=600)


class AISummaryContent(BaseModel):
    """What the model must return (validated before it reaches the client)."""

    purpose: str = Field(max_length=1500)
    architecture: str = Field(max_length=2500)
    key_modules: list[KeyModule] = Field(max_length=10)
    entry_points: list[str] = Field(max_length=10)
    maintenance_concerns: list[str] = Field(max_length=8)
    onboarding_steps: list[str] = Field(max_length=8)


class AISummary(AISummaryContent):
    provider: str
    model: str
    commit_sha: str
    generated_at: datetime
    disclaimer: str


class AIStatus(BaseModel):
    enabled: bool
    provider: str | None = None
    model: str | None = None
