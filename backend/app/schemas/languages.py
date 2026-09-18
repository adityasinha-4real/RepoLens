from typing import Literal

from pydantic import BaseModel

LanguageKind = Literal["programming", "markup", "data", "prose"]


class GitHubLanguageShare(BaseModel):
    """Byte counts from GitHub's linguist-based /languages endpoint."""

    language: str
    bytes: int
    percent: float


class LanguageStat(BaseModel):
    """Per-language statistics computed by RepoLens from the file tree."""

    language: str
    kind: LanguageKind
    files: int
    bytes: int
    percent_of_bytes: float  # share of bytes among files with a detected language
    lines: int  # counted lines for fetched files + estimate for the rest
    lines_estimated: bool  # True when any part of `lines` is an estimate
    sampled_files: int  # files whose content was downloaded and counted
    code_lines: int  # from sampled files only
    comment_lines: int
    blank_lines: int


class ExtensionStat(BaseModel):
    extension: str
    files: int
    bytes: int


class LanguageAnalysis(BaseModel):
    primary_language: str | None
    github_breakdown: list[GitHubLanguageShare]
    languages: list[LanguageStat]
    extensions: list[ExtensionStat]
    total_lines: int
    counted_lines: int
    estimated_lines: int
    sampled_files: int
    methodology: str
