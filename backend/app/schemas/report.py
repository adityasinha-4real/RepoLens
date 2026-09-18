from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.architecture import ArchitectureAnalysis
from app.schemas.dependencies import DependencyAnalysis
from app.schemas.documentation import DocumentationAnalysis
from app.schemas.health import HealthReport
from app.schemas.languages import LanguageAnalysis
from app.schemas.quality import QualityAnalysis
from app.schemas.repository import RateLimitInfo, RepositoryMetadata
from app.schemas.security import SecurityAnalysis
from app.schemas.structure import StructureAnalysis

REPORT_SCHEMA_VERSION = "1.0"


class AnalyzeRequest(BaseModel):
    repository_url: str = Field(
        min_length=1, max_length=512, examples=["https://github.com/psf/requests"]
    )


class FetchSummary(BaseModel):
    files_selected: int
    files_downloaded: int
    bytes_downloaded: int
    skipped_binary: int
    skipped_too_large: int
    failed: int
    budget_exhausted: bool
    raw_rate_limited: bool


class AnalysisLimits(BaseModel):
    max_tree_entries: int
    max_files_to_fetch: int
    max_file_bytes: int
    max_total_fetch_bytes: int


class AnalysisMeta(BaseModel):
    analyzed_at: datetime
    duration_ms: int
    commit_sha: str
    head_commit_date: datetime | None
    github_api_calls: int
    rate_limit: RateLimitInfo
    fetch: FetchSummary
    limits: AnalysisLimits
    partial: bool  # True when limits or truncation mean some data was not analyzed
    notes: list[str]
    engine_version: str


class AnalysisReport(BaseModel):
    schema_version: str = REPORT_SCHEMA_VERSION
    repository: RepositoryMetadata
    analysis: AnalysisMeta
    health: HealthReport
    structure: StructureAnalysis
    languages: LanguageAnalysis
    dependencies: DependencyAnalysis
    quality: QualityAnalysis
    documentation: DocumentationAnalysis
    security: SecurityAnalysis
    architecture: ArchitectureAnalysis
