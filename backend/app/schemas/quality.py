from typing import Literal

from pydantic import BaseModel


class MarkerItem(BaseModel):
    path: str
    line: int
    tag: str  # TODO | FIXME | HACK | XXX | BUG
    text: str


class LongFile(BaseModel):
    path: str
    lines: int
    estimated: bool  # True when derived from file size rather than counted


class CommentedCodeFile(BaseModel):
    path: str
    lines: int


class ComplexityItem(BaseModel):
    path: str
    name: str | None  # function name (Python) or None for file-level heuristics
    line: int | None
    complexity: int  # McCabe (Python) or decision-point count (heuristic)
    length: int  # lines in the function / file
    max_nesting: int | None = None
    method: Literal["python-ast", "heuristic"]


class Tooling(BaseModel):
    ci: list[str]
    linters: list[str]
    formatters: list[str]
    type_checkers: list[str]
    test_frameworks: list[str]
    pre_commit: bool
    editorconfig: bool


class QualityAnalysis(BaseModel):
    source_files: int
    test_files: int
    test_to_source_ratio: float | None
    source_bytes: int
    average_source_file_bytes: int
    sampled_source_files: int
    average_lines_per_sampled_file: float | None
    largest_source_files: list[LongFile]
    long_file_threshold: int
    long_files: list[LongFile]
    long_file_count: int
    marker_counts: dict[str, int]
    markers: list[MarkerItem]
    markers_truncated: bool
    commented_code_lines: int
    commented_code_files: list[CommentedCodeFile]
    complexity_threshold: int
    complexity_hotspots: list[ComplexityItem]
    high_complexity_count: int
    python_functions_analyzed: int
    tooling: Tooling
    coverage_note: str
    methodology: str
