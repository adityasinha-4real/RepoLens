from pydantic import BaseModel


class PresenceCheck(BaseModel):
    key: str
    label: str
    present: bool
    path: str | None = None


class ReadmeInfo(BaseModel):
    path: str
    format: str  # markdown | rst | text
    bytes: int
    words: int
    lines: int
    reading_minutes: float
    headings: list[str]
    sections: list[PresenceCheck]
    code_blocks: int
    links: int
    images: int
    badges: int
    has_table_of_contents: bool
    broken_relative_links: list[str]


class DirectoryInfo(BaseModel):
    path: str
    files: int
    doc_files: int = 0
    site_generator: str | None = None


class DocstringCoverage(BaseModel):
    public_definitions: int
    documented: int
    percent: float
    files_analyzed: int


class DocumentationAnalysis(BaseModel):
    readme: ReadmeInfo | None
    files: list[PresenceCheck]
    license_spdx: str | None
    license_name: str | None
    license_file: str | None
    docs_directory: DirectoryInfo | None
    examples_directory: DirectoryInfo | None
    comment_density: float | None  # comment / (code + comment) lines in downloaded code files
    python_docstrings: DocstringCoverage | None
    notes: list[str]
