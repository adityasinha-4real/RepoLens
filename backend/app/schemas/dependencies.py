from typing import Literal

from pydantic import BaseModel

Constraint = Literal["exact", "range", "none", "managed", "external"]


class Dependency(BaseModel):
    name: str
    version: str | None  # the specifier exactly as written in the manifest
    ecosystem: str
    scope: str  # production | development | optional | peer | build
    manifest: str
    source: str  # registry | git | path | url | workspace
    direct: bool = True
    constraint: Constraint
    # exact: pinned to one version; range: semver/specifier range; none: no constraint;
    # managed: version supplied elsewhere (Maven BOM/parent, Gradle catalog, unresolved property);
    # external: git/path/url/workspace source


class ManifestSummary(BaseModel):
    path: str
    ecosystem: str
    dependencies: int
    parse_error: str | None = None


class EcosystemSummary(BaseModel):
    ecosystem: str
    dependencies: int
    production: int
    development: int
    has_lockfile: bool


class VersionConflict(BaseModel):
    name: str
    ecosystem: str
    versions: list[str]
    manifests: list[str]


class DependencyAnalysis(BaseModel):
    total: int
    unique_packages: int
    production: int
    development: int
    other: int  # optional / peer / build
    unconstrained: int
    external_sources: int
    dependencies: list[Dependency]
    dependencies_truncated: bool
    manifests: list[ManifestSummary]
    manifests_not_analyzed: list[str]
    lockfiles: list[str]
    ecosystems: list[EcosystemSummary]
    version_conflicts: list[VersionConflict]
    vulnerability_data: str
    notes: list[str]
