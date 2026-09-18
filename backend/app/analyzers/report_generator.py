"""Deterministic, transparent repository health indicators.

Each dimension is a list of explicit checks with fixed point values. A dimension's score is
earned points / possible points x 100. The overall indicator is the unweighted mean of the
applicable dimensions. No AI is involved, and every check shows its evidence.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from app.analyzers.file_classifier import is_auxiliary_path
from app.schemas.architecture import ArchitectureAnalysis
from app.schemas.dependencies import DependencyAnalysis
from app.schemas.documentation import DocumentationAnalysis
from app.schemas.health import HealthCheck, HealthDimension, HealthReport
from app.schemas.quality import QualityAnalysis
from app.schemas.repository import RepositoryMetadata
from app.schemas.security import SecurityAnalysis
from app.schemas.structure import StructureAnalysis

METHODOLOGY = (
    "Each dimension is a fixed list of checks worth a set number of points. Its score is "
    "earned / possible points x 100. The overall indicator is the unweighted mean of the "
    "applicable dimensions. It is a summary of these specific, measurable checks, not a "
    "judgement of code correctness, security or quality. Content-based checks depend on the "
    "downloaded file sample. See each check for its evidence."
)


class _Dimension:
    def __init__(self, key: str, label: str) -> None:
        self.key, self.label = key, label
        self.checks: list[HealthCheck] = []

    def check(
        self, id_: str, label: str, max_points: float, passed: bool | float, detail: str
    ) -> None:
        """`passed` may be a fraction in [0, 1] for partial credit."""
        fraction = float(passed) if not isinstance(passed, bool) else (1.0 if passed else 0.0)
        fraction = min(1.0, max(0.0, fraction))
        self.checks.append(
            HealthCheck(
                id=f"{self.key}.{id_}",
                label=label,
                points=round(max_points * fraction, 1),
                max_points=max_points,
                passed=fraction >= 0.999,
                detail=detail,
            )
        )

    def build(self, summary: Callable[[int], str], applicable: bool = True) -> HealthDimension:
        possible = sum(c.max_points for c in self.checks)
        score = (
            round(100 * sum(c.points for c in self.checks) / possible)
            if applicable and possible
            else None
        )
        return HealthDimension(
            key=self.key,
            label=self.label,
            score=score,
            applicable=applicable and score is not None,
            checks=self.checks,
            summary=summary(score) if score is not None else "Not applicable to this repository.",
        )


def _band(score: int) -> str:
    return "strong" if score >= 80 else "moderate" if score >= 50 else "weak"


def _documentation(doc: DocumentationAnalysis) -> HealthDimension:
    d = _Dimension("documentation", "Documentation")
    readme = doc.readme
    d.check(
        "readme",
        "README present",
        20,
        readme is not None,
        readme.path if readme else "No README found.",
    )
    words = readme.words if readme else 0
    d.check(
        "readme_depth", "README has at least 300 words", 10, min(1.0, words / 300), f"{words} words"
    )
    sections = {s.key: s.present for s in readme.sections} if readme else {}
    d.check(
        "install",
        "README explains installation/setup",
        10,
        sections.get("install", False),
        "Installation section found."
        if sections.get("install")
        else "No installation section heading found.",
    )
    d.check(
        "usage",
        "README explains usage",
        10,
        sections.get("usage", False),
        "Usage section found."
        if sections.get("usage")
        else "No usage/example section heading found.",
    )
    d.check(
        "license",
        "License declared",
        20,
        bool(doc.license_spdx or doc.license_file),
        doc.license_spdx or doc.license_file or "No license detected.",
    )
    files = {f.key: f for f in doc.files}
    d.check(
        "contributing",
        "Contributing guide",
        10,
        files["contributing"].present,
        files["contributing"].path or "No CONTRIBUTING file.",
    )
    has_docs = doc.docs_directory is not None and doc.docs_directory.doc_files > 0
    d.check(
        "docs",
        "Dedicated documentation",
        10,
        has_docs,
        f"{doc.docs_directory.path}/ with {doc.docs_directory.doc_files} doc files"
        if has_docs and doc.docs_directory
        else "No docs/ directory with documentation.",
    )
    d.check(
        "changelog",
        "Changelog",
        10,
        files["changelog"].present,
        files["changelog"].path or "No changelog file.",
    )
    return d.build(lambda s: f"Documentation coverage is {_band(s)}.")


def _tests(quality: QualityAnalysis) -> HealthDimension:
    d = _Dimension("tests", "Test presence")
    d.check(
        "tests_exist",
        "Test files present",
        40,
        quality.test_files > 0,
        f"{quality.test_files} test files",
    )
    ratio = quality.test_to_source_ratio or 0.0
    d.check(
        "ratio",
        "Test-to-source file ratio of at least 0.2",
        20,
        min(1.0, ratio / 0.2),
        f"ratio {ratio:.2f}" if quality.test_to_source_ratio is not None else "no source files",
    )
    frameworks = quality.tooling.test_frameworks
    d.check(
        "framework",
        "Test framework configured",
        20,
        bool(frameworks),
        ", ".join(frameworks) or "No test framework detected.",
    )
    d.check(
        "ci",
        "Continuous integration configured",
        20,
        bool(quality.tooling.ci),
        ", ".join(quality.tooling.ci) or "No CI configuration found.",
    )
    applicable = quality.source_files > 0
    return d.build(
        lambda s: (
            f"Test presence is {_band(s)}. This measures whether tests "
            "exist, not whether they pass or what they cover."
        ),
        applicable,
    )


def _organization(quality: QualityAnalysis) -> HealthDimension:
    d = _Dimension("organization", "Code organization")
    sampled = max(quality.sampled_source_files, 1)
    long_share = quality.long_file_count / max(quality.source_files, 1)
    d.check(
        "long_files",
        "5% or fewer source files exceed 500 lines",
        25,
        1.0 if long_share <= 0.05 else max(0.0, 1 - (long_share - 0.05) / 0.2),
        f"{quality.long_file_count} of {quality.source_files} files ({long_share:.0%})",
    )
    hotspots = quality.high_complexity_count
    d.check(
        "complexity",
        "Few high-complexity hotspots in downloaded files",
        25,
        1.0 if hotspots <= max(1, sampled // 50) else max(0.0, 1 - hotspots / sampled * 5),
        f"{hotspots} hotspots across {quality.sampled_source_files} downloaded source files",
    )
    d.check(
        "linter",
        "Linter configured",
        25,
        bool(quality.tooling.linters),
        ", ".join(quality.tooling.linters) or "No linter configuration detected.",
    )
    formatting = quality.tooling.formatters or (
        ["EditorConfig"] if quality.tooling.editorconfig else []
    )
    d.check(
        "formatter",
        "Formatter or EditorConfig configured",
        15,
        bool(formatting),
        ", ".join(formatting) or "No formatter configuration detected.",
    )
    markers = sum(quality.marker_counts.values())
    d.check(
        "markers",
        "Low TODO/FIXME density (5 or fewer per downloaded file)",
        10,
        markers / sampled <= 5,
        f"{markers} markers in {quality.sampled_source_files} files",
    )
    return d.build(
        lambda s: f"Code organization indicators are {_band(s)}.", quality.source_files > 0
    )


def _dependencies(deps: DependencyAnalysis, security: SecurityAnalysis) -> HealthDimension:
    d = _Dimension("dependencies", "Dependency hygiene")
    errors = [m.path for m in deps.manifests if m.parse_error]
    d.check(
        "parseable",
        "Manifests parse cleanly",
        20,
        not errors,
        f"Parse errors in: {', '.join(errors[:3])}"
        if errors
        else f"{len(deps.manifests)} manifest(s) parsed",
    )
    ecosystems = deps.ecosystems
    locked = [e.ecosystem for e in ecosystems if e.has_lockfile]
    lockable = [e for e in ecosystems if e.ecosystem not in ("Maven",)]
    d.check(
        "lockfiles",
        "Lockfile for each ecosystem",
        30,
        (sum(e.has_lockfile for e in lockable) / len(lockable)) if lockable else 1.0,
        f"Locked: {', '.join(locked) or 'none'}; ecosystems: "
        f"{', '.join(e.ecosystem for e in ecosystems)}",
    )
    share = deps.unconstrained / deps.total if deps.total else 0
    d.check(
        "constraints",
        "10% or fewer dependencies without a version constraint",
        20,
        share <= 0.1,
        f"{deps.unconstrained} of {deps.total} unconstrained",
    )
    d.check(
        "conflicts",
        "No conflicting version declarations",
        15,
        not deps.version_conflicts,
        f"{len(deps.version_conflicts)} package(s) declared with different versions",
    )
    updates = next((h for h in security.hygiene if h.key == "dependency_updates"), None)
    d.check(
        "updates",
        "Automated dependency updates",
        15,
        bool(updates and updates.passed),
        updates.detail if updates else "",
    )
    return d.build(
        lambda s: f"Dependency hygiene is {_band(s)}. No vulnerability database was consulted.",
        deps.total > 0 or bool(deps.manifests),
    )


def _activity(
    meta: RepositoryMetadata, head_commit_date: datetime | None, now: datetime
) -> HealthDimension:
    d = _Dimension("activity", "Repository activity")
    pushed = meta.pushed_at
    if pushed is not None:
        days = (now - pushed).days
        fraction = 1.0 if days <= 30 else 0.8 if days <= 90 else 0.4 if days <= 365 else 0.0
        d.check(
            "recent_push",
            "Pushed within the last 30 days (partial credit up to a year)",
            50,
            fraction,
            f"last push {days} days ago",
        )
    else:
        d.check("recent_push", "Pushed recently", 50, False, "Push date unknown")
    d.check(
        "not_archived",
        "Repository is not archived",
        30,
        not meta.archived,
        "Archived (read-only)" if meta.archived else "Active (not archived)",
    )
    if head_commit_date is not None:
        days = (now - head_commit_date).days
        d.check(
            "recent_commit",
            "Default branch committed to within 180 days",
            20,
            days <= 180,
            f"last commit {days} days ago",
        )
    else:
        d.check(
            "recent_commit",
            "Default branch committed to within 180 days",
            20,
            False,
            "Commit date unknown",
        )
    return d.build(
        lambda s: f"Activity is {_band(s)}, based on the last push and last commit dates only."
    )


def _security(security: SecurityAnalysis) -> HealthDimension:
    d = _Dimension("security", "Security indicators")
    high = [f for f in security.findings if f.severity == "high" and not f.in_test]
    medium = [f for f in security.findings if f.severity == "medium" and not f.in_test]
    d.check(
        "no_high",
        "No high-severity indicators (outside tests)",
        35,
        not high,
        f"{len(high)} high-severity indicator(s)",
    )
    d.check(
        "few_medium",
        "3 or fewer medium-severity indicators (outside tests)",
        20,
        len(medium) <= 3,
        f"{len(medium)} medium-severity indicator(s)",
    )
    sensitive = [
        f
        for f in security.findings
        if f.category == "sensitive-file" and not f.in_test and f.severity in ("high", "medium")
    ]
    d.check(
        "no_sensitive_files",
        "No committed sensitive files",
        15,
        not sensitive,
        f"{len(sensitive)} sensitive file(s)" if sensitive else "None detected",
    )
    hygiene = {h.key: h for h in security.hygiene}
    policy = hygiene["security_policy"]
    d.check("policy", "Security policy published", 15, policy.passed, policy.detail)
    gitignore_ok = hygiene["gitignore"].passed and (
        "gitignore_env" not in hygiene
        or hygiene["gitignore_env"].passed
        or not security.env_variables
    )
    d.check(
        "gitignore",
        ".gitignore protects local secrets",
        15,
        gitignore_ok,
        hygiene.get("gitignore_env", hygiene["gitignore"]).detail,
    )
    return d.build(
        lambda s: (
            f"Static security indicators are {_band(s)}. This is not a "
            "security assessment, and the repository is not verified as secure."
        )
    )


def _structure(
    structure: StructureAnalysis, quality: QualityAnalysis, architecture: ArchitectureAnalysis
) -> HealthDimension:
    d = _Dimension("structure", "Project structure")
    # Fixture projects inside tests/examples legitimately contain node_modules etc.
    committed = [
        i.path
        for i in structure.ignored_directories
        if i.path.split("/")[-1]
        in ("node_modules", "venv", ".venv", "__pycache__", "dist", "build", "target", "coverage")
        and not is_auxiliary_path(i.path + "/")
    ]
    d.check(
        "no_artifacts",
        "No committed dependency/build directories",
        25,
        not committed,
        f"Committed: {', '.join(committed[:4])}" if committed else "None detected",
    )
    root_source = next((m.source_files for m in architecture.modules if m.id == "."), 0)
    share = root_source / quality.source_files if quality.source_files else 0
    d.check(
        "source_layout",
        "Source organized into directories",
        25,
        quality.source_files <= 10 or share <= 0.5,
        f"{root_source} of {quality.source_files} source files at the repository root",
    )
    test_dir = any(m.role == "Tests" for m in architecture.modules) or quality.test_files > 0
    d.check(
        "tests_separated",
        "Tests are identifiable",
        20,
        test_dir,
        "Test files or directories found" if test_dir else "No test files found",
    )
    d.check(
        "depth",
        "Directory depth of 10 or less (outside tests and examples)",
        10,
        structure.product_max_depth <= 10,
        f"max depth {structure.product_max_depth}",
    )
    gitignore = any(t.name == ".gitignore" for t in structure.top_level)
    d.check(
        "gitignore", "Root .gitignore present", 10, gitignore, "Present" if gitignore else "Missing"
    )
    d.check(
        "entry_point",
        "Entry point identifiable",
        10,
        bool(architecture.entry_points),
        architecture.entry_points[0].path
        if architecture.entry_points
        else "No entry point detected",
    )
    return d.build(lambda s: f"Project structure indicators are {_band(s)}.")


def build_health_report(
    *,
    metadata: RepositoryMetadata,
    head_commit_date: datetime | None,
    structure: StructureAnalysis,
    quality: QualityAnalysis,
    dependencies: DependencyAnalysis,
    documentation: DocumentationAnalysis,
    security: SecurityAnalysis,
    architecture: ArchitectureAnalysis,
    now: datetime | None = None,
) -> HealthReport:
    now = now or datetime.now(UTC)
    dimensions = [
        _documentation(documentation),
        _organization(quality),
        _tests(quality),
        _dependencies(dependencies, security),
        _activity(metadata, head_commit_date, now),
        _security(security),
        _structure(structure, quality, architecture),
    ]
    scores = [d.score for d in dimensions if d.applicable and d.score is not None]
    return HealthReport(
        overall=round(sum(scores) / len(scores)) if scores else None,
        dimensions=dimensions,
        methodology=METHODOLOGY,
    )
