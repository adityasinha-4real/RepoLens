"""Aggregate parsed manifests into a dependency report."""

import logging
import re
from collections import defaultdict
from pathlib import PurePosixPath

from app.analyzers.dependency_parsers import ManifestParseError, ParsedDependency, parser_for
from app.analyzers.file_classifier import LOCKFILES, ignored_segment
from app.schemas.dependencies import (
    Constraint,
    Dependency,
    DependencyAnalysis,
    EcosystemSummary,
    ManifestSummary,
    VersionConflict,
)
from app.services.repository_tree import RepositoryTree

logger = logging.getLogger(__name__)

MAX_REPORTED_DEPENDENCIES = 2000
VULNERABILITY_NOTE = (
    "RepoLens has not checked these dependencies against a vulnerability database. "
    "Use a tool such as OSV-Scanner, npm audit or pip-audit for vulnerability data."
)

_LOCKFILE_ECOSYSTEM = {
    "package-lock.json": "npm",
    "yarn.lock": "npm",
    "pnpm-lock.yaml": "npm",
    "bun.lockb": "npm",
    "bun.lock": "npm",
    "npm-shrinkwrap.json": "npm",
    "poetry.lock": "PyPI",
    "Pipfile.lock": "PyPI",
    "uv.lock": "PyPI",
    "pdm.lock": "PyPI",
    "Cargo.lock": "crates.io",
    "go.sum": "Go",
    "composer.lock": "Packagist",
    "Gemfile.lock": "RubyGems",
    "gradle.lockfile": "Maven",
}
_SEMVER_EXACT = re.compile(r"^v?\d+(\.\d+){0,3}([-+][\w.]+)?$")


def classify_constraint(dep: ParsedDependency, ecosystem: str) -> Constraint:
    if dep.source != "registry":
        return "external"
    v = (dep.version or "").strip()
    if not v:
        return "managed" if ecosystem == "Maven" else "none"
    if v in {"*", "latest", "x", "X", "any"}:
        return "none"
    if "${" in v or v.startswith("$"):
        return "managed"
    if ecosystem == "PyPI":
        if v.startswith("===") or (v.startswith("==") and "*" not in v and "," not in v):
            return "exact"
        return "range"
    if ecosystem == "Go":
        return "exact"
    if ecosystem == "crates.io":
        return "exact" if v.startswith("=") and not v.startswith("=>") else "range"
    if ecosystem == "Maven":
        if v.startswith("[") and v.endswith("]") and "," not in v:
            return "exact"
        return "range" if v[:1] in "[(" else "exact"
    if ecosystem == "RubyGems":
        v2 = v.lstrip("= ").strip()
        return "exact" if _SEMVER_EXACT.match(v2) and not v.startswith(("~", ">", "<")) else "range"
    # npm, Packagist: bare versions are exact, anything with operators is a range
    return "exact" if _SEMVER_EXACT.match(v.lstrip("=")) else "range"


def analyze_dependencies(tree: RepositoryTree, contents: dict[str, str]) -> DependencyAnalysis:
    manifests: list[ManifestSummary] = []
    not_analyzed: list[str] = []
    deps: list[Dependency] = []
    lockfiles: list[str] = []
    lock_ecosystems: set[str] = set()

    for entry in tree.files():
        if ignored_segment(entry.path) is not None:
            continue
        name = PurePosixPath(entry.path).name
        if name in LOCKFILES:
            lockfiles.append(entry.path)
            if name in _LOCKFILE_ECOSYSTEM:
                lock_ecosystems.add(_LOCKFILE_ECOSYSTEM[name])
            continue
        parser = parser_for(entry.path)
        if parser is None:
            continue
        ecosystem, parse = parser
        text = contents.get(entry.path)
        if text is None:
            not_analyzed.append(entry.path)
            continue
        try:
            parsed = parse(text, entry.path)
        except ManifestParseError as exc:
            manifests.append(
                ManifestSummary(
                    path=entry.path, ecosystem=ecosystem, dependencies=0, parse_error=str(exc)[:200]
                )
            )
            continue
        except Exception as exc:  # a parser bug must not abort the whole analysis
            logger.warning("Unexpected error parsing %s: %r", entry.path, exc)
            manifests.append(
                ManifestSummary(
                    path=entry.path,
                    ecosystem=ecosystem,
                    dependencies=0,
                    parse_error="could not be parsed",
                )
            )
            continue
        # setup.cfg/pyproject files without dependency sections are not manifests per se
        if not parsed and PurePosixPath(entry.path).name == "setup.cfg":
            continue
        manifests.append(
            ManifestSummary(path=entry.path, ecosystem=ecosystem, dependencies=len(parsed))
        )
        for p in parsed:
            source = "workspace" if (p.version or "").startswith("workspace:") else p.source
            p = ParsedDependency(
                p.name[:200], (p.version or None) and p.version[:100], p.scope, source, p.direct
            )
            deps.append(
                Dependency(
                    name=p.name,
                    version=p.version,
                    ecosystem=ecosystem,
                    scope=p.scope,
                    manifest=entry.path,
                    source=p.source,
                    direct=p.direct,
                    constraint=classify_constraint(p, ecosystem),
                )
            )

    # Version conflicts: the same package declared with different specifiers across manifests.
    declared: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for d in deps:
        if d.version and d.source == "registry":
            declared[(d.ecosystem, d.name.lower())][d.version].add(d.manifest)
    conflicts = []
    for (ecosystem, lowered), versions in declared.items():
        if len(versions) > 1:
            names = {d.name for d in deps if d.ecosystem == ecosystem and d.name.lower() == lowered}
            conflicts.append(
                VersionConflict(
                    name=sorted(names)[0],
                    ecosystem=ecosystem,
                    versions=sorted(versions),
                    manifests=sorted({m for ms in versions.values() for m in ms}),
                )
            )
    conflicts.sort(key=lambda c: (-len(c.versions), c.name))

    eco_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for d in deps:
        s = eco_stats[d.ecosystem]
        s[0] += 1
        s[1] += d.scope == "production"
        s[2] += d.scope == "development"

    notes: list[str] = []
    if not_analyzed:
        notes.append(
            f"{len(not_analyzed)} manifest(s) were not downloaded (size or budget "
            "limits) and are not included."
        )
    if any(m.path.endswith(("build.gradle", "build.gradle.kts")) for m in manifests):
        notes.append(
            "Gradle version-catalog aliases (libs.*) cannot be resolved statically "
            "and are not listed."
        )

    production = sum(d.scope == "production" for d in deps)
    development = sum(d.scope == "development" for d in deps)
    return DependencyAnalysis(
        total=len(deps),
        unique_packages=len({(d.ecosystem, d.name.lower()) for d in deps}),
        production=production,
        development=development,
        other=len(deps) - production - development,
        unconstrained=sum(d.constraint == "none" for d in deps),
        external_sources=sum(d.constraint == "external" for d in deps),
        dependencies=deps[:MAX_REPORTED_DEPENDENCIES],
        dependencies_truncated=len(deps) > MAX_REPORTED_DEPENDENCIES,
        manifests=manifests,
        manifests_not_analyzed=not_analyzed,
        lockfiles=sorted(lockfiles),
        ecosystems=sorted(
            (
                EcosystemSummary(
                    ecosystem=e,
                    dependencies=s[0],
                    production=s[1],
                    development=s[2],
                    has_lockfile=e in lock_ecosystems,
                )
                for e, s in eco_stats.items()
            ),
            key=lambda e: (-e.dependencies, e.ecosystem),
        ),
        version_conflicts=conflicts[:50],
        vulnerability_data=VULNERABILITY_NOTE,
        notes=notes,
    )
