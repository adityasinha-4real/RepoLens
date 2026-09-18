from pydantic import BaseModel


class Detection(BaseModel):
    name: str
    category: str  # frontend | backend | mobile | desktop | cli | ml | data | orm | build | ...
    evidence: str  # where it was detected, e.g. "package.json dependency 'next'"


class EntryPoint(BaseModel):
    path: str
    kind: str
    evidence: str


class Module(BaseModel):
    id: str
    path: str  # "" for repository-root files
    name: str
    role: str
    role_source: str  # "workspace-package" | "directory-name" | "unknown"
    files: int
    source_files: int
    bytes: int
    languages: list[str]
    sampled_files: int


class ModuleEdge(BaseModel):
    source: str
    target: str
    imports: int  # resolved import statements from source files into target files


class FileHub(BaseModel):
    path: str
    imported_by: int


class ComposeService(BaseModel):
    name: str
    image: str | None = None
    build: bool = False
    depends_on: list[str] = []


class InfraItem(BaseModel):
    kind: str
    path: str
    detail: str


class ImportResolution(BaseModel):
    files_parsed: int
    imports_found: int
    internal_resolved: int
    external: int
    unresolved: int
    languages: list[str]


class ArchitectureAnalysis(BaseModel):
    project_types: list[Detection]
    frameworks: list[Detection]
    monorepo_tool: str | None
    workspace_packages: list[str]
    entry_points: list[EntryPoint]
    modules: list[Module]
    edges: list[ModuleEdge]
    hubs: list[FileHub]
    compose_services: list[ComposeService]
    infrastructure: list[InfraItem]
    import_resolution: ImportResolution
    methodology: str
    notes: list[str]
