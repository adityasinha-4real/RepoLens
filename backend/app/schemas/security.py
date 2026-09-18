from typing import Literal

from pydantic import BaseModel

Severity = Literal["high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]


class SecurityFinding(BaseModel):
    rule: str
    title: str
    severity: Severity
    confidence: Confidence
    category: str
    path: str
    line: int | None = None
    evidence: str | None = None  # secrets are always redacted
    description: str
    in_test: bool = False


class SecurityRule(BaseModel):
    id: str
    title: str
    severity: Severity
    category: str
    description: str


class HygieneCheck(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str


class SecurityAnalysis(BaseModel):
    disclaimer: str
    findings: list[SecurityFinding]
    findings_truncated: bool
    counts_by_severity: dict[str, int]
    counts_by_category: dict[str, int]
    files_scanned: int
    env_variables: list[str]
    env_variable_files: int
    hygiene: list[HygieneCheck]
    rules: list[SecurityRule]
    coverage_note: str
