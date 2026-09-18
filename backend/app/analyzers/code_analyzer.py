"""Deterministic code-quality indicators.

Content-based metrics (markers, commented-out code, complexity, counted lines) cover only the
files whose content was downloaded. The report states that coverage explicitly.
"""

import ast
import re
from collections import Counter
from pathlib import PurePosixPath

from app.analyzers.file_classifier import FileCategory, classify, ignored_segment
from app.analyzers.line_counter import line_comment_prefixes
from app.schemas.quality import (
    CommentedCodeFile,
    ComplexityItem,
    LongFile,
    MarkerItem,
    QualityAnalysis,
    Tooling,
)
from app.services.repository_tree import RepositoryTree

LONG_FILE_LINES = 500
COMPLEXITY_THRESHOLD = 10  # McCabe; widely used default (e.g. flake8's mccabe plugin)
HEURISTIC_DECISIONS_THRESHOLD = 100
HEURISTIC_NESTING_THRESHOLD = 6
ESTIMATE_BYTES_PER_LINE = 40
MAX_MARKERS = 300

METHODOLOGY = (
    "Python functions are measured with McCabe cyclomatic complexity computed from the "
    "abstract syntax tree (the code is parsed, never executed); functions above "
    f"{COMPLEXITY_THRESHOLD} are flagged. For other brace-based languages RepoLens uses a "
    "file-level heuristic: decision keywords/operators and maximum brace nesting, flagged at "
    f"{HEURISTIC_DECISIONS_THRESHOLD}+ decision points or nesting {HEURISTIC_NESTING_THRESHOLD}+. "
    f"Long files have more than {LONG_FILE_LINES} lines (estimated from size at "
    f"{ESTIMATE_BYTES_PER_LINE} bytes/line when not downloaded). Commented-out code is detected "
    "heuristically as runs of 2+ consecutive comment lines that look like code."
)

_MARKER_RE = re.compile(
    r"(?:#|//|/\*|<!--|--|;|^\s*\*)[^\n]*?\b(?P<tag>TODO|FIXME|HACK|XXX)\b(?P<rest>[^\n]*)"
)
_CODE_LIKE_RE = re.compile(
    r"""^(?:
        (?:if|for|while|return|import|from|def|class|function|const|let|var|public|private|
           protected|static|else|elif|try|catch|except|switch|case|print|console\.\w+)\b.*
      | .*[;{}]\s*$
      | [\w.\[\]]+\s*=\s*[^=].*
      | [\w.]+\(.*\)\s*;?\s*$
    )""",
    re.VERBOSE,
)
# fmt: off
_BRACE_LANGUAGES = frozenset({
    "JavaScript", "TypeScript", "Java", "Kotlin", "Scala", "Go", "Rust", "C", "C++", "C#",
    "Swift", "Dart", "PHP", "Groovy", "Objective-C", "Objective-C++", "Vue", "Svelte",
})
# fmt: on
_DECISION_RE = re.compile(r"\b(?:if|for|while|case|catch|elif|elsif|unless|until)\b|&&|\|\|")
_STRING_OR_COMMENT_RE = re.compile(
    r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`",
    re.DOTALL,
)


# --- markers & commented code ------------------------------------------------------


def find_markers(path: str, text: str) -> list[MarkerItem]:
    items = []
    for number, line in enumerate(text.splitlines(), start=1):
        if "TODO" not in line and "FIXME" not in line and "HACK" not in line and "XXX" not in line:
            continue
        m = _MARKER_RE.search(line)
        if m:
            rest = m.group("rest").strip().removesuffix("*/").removesuffix("-->").strip()
            rest = re.sub(r"^[\s:(\-]+", "", rest)
            text_out = f"{m.group('tag')}{': ' + rest if rest else ''}"
            items.append(
                MarkerItem(path=path, line=number, tag=m.group("tag"), text=text_out[:160])
            )
    return items


def count_commented_code(text: str, language: str | None) -> int:
    prefixes = line_comment_prefixes(language)
    if not prefixes:
        return 0
    total = run = 0
    for raw in text.splitlines():
        line = raw.strip()
        body = None
        for prefix in prefixes:
            if line.startswith(prefix):
                body = line[len(prefix) :].strip()
                break
        if body and not body.startswith(("!", "#", "/", "@", "*")) and _CODE_LIKE_RE.match(body):
            run += 1
            continue
        if run >= 2:
            total += run
        run = 0
    if run >= 2:
        total += run
    return total


# --- complexity -------------------------------------------------------------------


def _mccabe(func: ast.AST) -> int:
    """Cyclomatic complexity of one function, excluding nested function/class bodies."""
    complexity = 1
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(
            node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)
        ):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            complexity += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            complexity += 1
        stack.extend(ast.iter_child_nodes(node))
    return complexity


def python_function_complexity(path: str, text: str) -> list[ComplexityItem] | None:
    """Return per-function complexity, or None when the file cannot be parsed."""
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    items: list[ComplexityItem] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                end = getattr(child, "end_lineno", None) or child.lineno
                items.append(
                    ComplexityItem(
                        path=path,
                        name=name,
                        line=child.lineno,
                        complexity=_mccabe(child),
                        length=end - child.lineno + 1,
                        method="python-ast",
                    )
                )
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    try:
        visit(tree, "")
    except RecursionError:
        return None
    return items


def brace_heuristic(path: str, text: str) -> ComplexityItem:
    stripped = _STRING_OR_COMMENT_RE.sub('""', text)
    decisions = len(_DECISION_RE.findall(stripped))
    depth = max_depth = 0
    for ch in stripped:
        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return ComplexityItem(
        path=path,
        name=None,
        line=None,
        complexity=decisions,
        length=text.count("\n") + 1,
        max_nesting=max_depth,
        method="heuristic",
    )


# --- tooling ------------------------------------------------------------------------


def detect_tooling(
    paths: list[str], contents: dict[str, str], dependency_names: set[str]
) -> Tooling:
    names = {PurePosixPath(p).name for p in paths}
    lower_names = {n.lower() for n in names}
    deps = {d.lower() for d in dependency_names}
    pyproject = "\n".join(t for p, t in contents.items() if p.endswith("pyproject.toml"))

    def has(*candidates: str) -> bool:
        return any(c.lower() in lower_names for c in candidates)

    def has_prefix(*prefixes: str) -> bool:
        return any(n.startswith(prefixes) for n in lower_names)

    def tool(section: str) -> bool:
        return f"[tool.{section}" in pyproject

    ci = []
    if any(p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")) for p in paths):
        ci.append("GitHub Actions")
    for filename, provider in (
        (".gitlab-ci.yml", "GitLab CI"),
        (".travis.yml", "Travis CI"),
        ("azure-pipelines.yml", "Azure Pipelines"),
        ("Jenkinsfile", "Jenkins"),
        ("bitbucket-pipelines.yml", "Bitbucket Pipelines"),
        (".drone.yml", "Drone"),
    ):
        if filename in names:
            ci.append(provider)
    if any(p.startswith(".circleci/") for p in paths):
        ci.append("CircleCI")
    if any(p.startswith(".buildkite/") for p in paths):
        ci.append("Buildkite")

    checks: dict[str, list[tuple[str, bool]]] = {
        "linters": [
            ("ESLint", has_prefix(".eslintrc", "eslint.config") or "eslint" in deps),
            ("Ruff", has("ruff.toml", ".ruff.toml") or tool("ruff") or "ruff" in deps),
            ("Flake8", has(".flake8") or "flake8" in deps),
            ("Pylint", has(".pylintrc", "pylintrc") or tool("pylint") or "pylint" in deps),
            ("RuboCop", has(".rubocop.yml") or "rubocop" in deps),
            ("golangci-lint", has(".golangci.yml", ".golangci.yaml", ".golangci.toml")),
            ("Clippy", has("clippy.toml", ".clippy.toml")),
            ("Stylelint", has_prefix(".stylelintrc", "stylelint.config")),
            ("Biome", has("biome.json", "biome.jsonc")),
            ("Checkstyle", has("checkstyle.xml")),
            ("SwiftLint", has(".swiftlint.yml")),
            ("detekt", has("detekt.yml", "detekt.yaml")),
            ("PHP_CodeSniffer", has("phpcs.xml", "phpcs.xml.dist", ".phpcs.xml")),
            ("Hadolint", has(".hadolint.yaml", ".hadolint.yml")),
            ("markdownlint", has_prefix(".markdownlint")),
        ],
        "formatters": [
            ("Prettier", has_prefix(".prettierrc", "prettier.config") or "prettier" in deps),
            ("Black", tool("black") or "black" in deps),
            ("isort", tool("isort") or has(".isort.cfg") or "isort" in deps),
            ("Ruff formatter", tool("ruff.format")),
            ("rustfmt", has("rustfmt.toml", ".rustfmt.toml")),
            ("clang-format", has(".clang-format")),
            ("Biome", has("biome.json", "biome.jsonc")),
            ("dprint", has("dprint.json", ".dprint.json")),
        ],
        "type_checkers": [
            ("TypeScript", has("tsconfig.json") or "typescript" in deps),
            ("mypy", has("mypy.ini", ".mypy.ini") or tool("mypy") or "mypy" in deps),
            ("Pyright", has("pyrightconfig.json") or tool("pyright") or "pyright" in deps),
            ("Flow", has(".flowconfig")),
            ("PHPStan", has("phpstan.neon", "phpstan.neon.dist")),
            ("Psalm", has("psalm.xml", "psalm.xml.dist")),
        ],
        "test_frameworks": [
            ("pytest", has("pytest.ini", "conftest.py") or tool("pytest") or "pytest" in deps),
            ("Jest", has_prefix("jest.config") or "jest" in deps),
            ("Vitest", has_prefix("vitest.config") or "vitest" in deps),
            ("Mocha", has_prefix(".mocharc") or "mocha" in deps),
            ("Playwright", has_prefix("playwright.config") or "@playwright/test" in deps),
            ("Cypress", has_prefix("cypress.config") or has("cypress.json") or "cypress" in deps),
            ("JUnit", any("junit" in d for d in deps)),
            ("RSpec", has(".rspec") or "rspec" in deps or "rspec-rails" in deps),
            ("PHPUnit", has("phpunit.xml", "phpunit.xml.dist") or "phpunit/phpunit" in deps),
            ("Go testing", any(p.endswith("_test.go") for p in paths)),
            ("Karma", has_prefix("karma.conf")),
        ],
    }
    found = {k: [name for name, ok in v if ok] for k, v in checks.items()}
    return Tooling(
        ci=ci,
        linters=found["linters"],
        formatters=found["formatters"],
        type_checkers=found["type_checkers"],
        test_frameworks=found["test_frameworks"],
        pre_commit=has(".pre-commit-config.yaml", ".husky")
        or any(p.startswith(".husky/") for p in paths),
        editorconfig=has(".editorconfig"),
    )


# --- orchestration ---------------------------------------------------------------------


def analyze_code(
    tree: RepositoryTree, contents: dict[str, str], dependency_names: set[str]
) -> QualityAnalysis:
    paths = [e.path for e in tree.files() if ignored_segment(e.path) is None]
    source_sizes: dict[str, int] = {}
    test_files = 0
    markers: list[MarkerItem] = []
    marker_counts: Counter[str] = Counter()
    commented: list[CommentedCodeFile] = []
    complexity: list[ComplexityItem] = []
    python_functions = 0
    sampled_lines: list[int] = []
    long_files: list[LongFile] = []
    size_by_path = {e.path: e.size for e in tree.files()}

    for path in paths:
        cls = classify(path)
        if cls.category == FileCategory.TEST:
            test_files += 1
        text = contents.get(path)
        is_code = cls.category in (FileCategory.SOURCE, FileCategory.TEST)
        if cls.category == FileCategory.SOURCE:
            source_sizes[path] = size_by_path[path]
            lines = text.count("\n") + 1 if text is not None else None
            if lines is not None:
                sampled_lines.append(lines)
            estimated = lines is None
            lines = lines if lines is not None else size_by_path[path] // ESTIMATE_BYTES_PER_LINE
            if lines > LONG_FILE_LINES:
                long_files.append(LongFile(path=path, lines=lines, estimated=estimated))

        if text is None or not (is_code or cls.category == FileCategory.CONFIG):
            continue
        for item in find_markers(path, text):
            marker_counts[item.tag] += 1
            if len(markers) < MAX_MARKERS:
                markers.append(item)
        if not is_code:
            continue
        commented_lines = count_commented_code(text, cls.language)
        if commented_lines:
            commented.append(CommentedCodeFile(path=path, lines=commented_lines))
        if cls.language == "Python":
            functions = python_function_complexity(path, text)
            if functions:
                python_functions += len(functions)
                complexity.extend(f for f in functions if f.complexity > COMPLEXITY_THRESHOLD)
        elif cls.language in _BRACE_LANGUAGES and cls.category == FileCategory.SOURCE:
            item = brace_heuristic(path, text)
            if (
                item.complexity >= HEURISTIC_DECISIONS_THRESHOLD
                or (item.max_nesting or 0) >= HEURISTIC_NESTING_THRESHOLD
            ):
                complexity.append(item)

    complexity.sort(key=lambda c: (c.method != "python-ast", -c.complexity, c.path))
    long_files.sort(key=lambda f: (-f.lines, f.path))
    commented.sort(key=lambda c: (-c.lines, c.path))
    source_files = len(source_sizes)
    source_bytes = sum(source_sizes.values())
    sampled_source = len(sampled_lines)
    largest = sorted(source_sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    return QualityAnalysis(
        source_files=source_files,
        test_files=test_files,
        test_to_source_ratio=round(test_files / source_files, 3) if source_files else None,
        source_bytes=source_bytes,
        average_source_file_bytes=source_bytes // source_files if source_files else 0,
        sampled_source_files=sampled_source,
        average_lines_per_sampled_file=(
            round(sum(sampled_lines) / sampled_source, 1) if sampled_source else None
        ),
        largest_source_files=[
            LongFile(
                path=p,
                lines=(contents[p].count("\n") + 1)
                if p in contents
                else s // ESTIMATE_BYTES_PER_LINE,
                estimated=p not in contents,
            )
            for p, s in largest
        ],
        long_file_threshold=LONG_FILE_LINES,
        long_files=long_files[:25],
        long_file_count=len(long_files),
        marker_counts={tag: marker_counts.get(tag, 0) for tag in ("TODO", "FIXME", "HACK", "XXX")},
        markers=markers,
        markers_truncated=sum(marker_counts.values()) > len(markers),
        commented_code_lines=sum(c.lines for c in commented),
        commented_code_files=commented[:15],
        complexity_threshold=COMPLEXITY_THRESHOLD,
        complexity_hotspots=complexity[:30],
        high_complexity_count=len(complexity),
        python_functions_analyzed=python_functions,
        tooling=detect_tooling(paths, contents, dependency_names),
        coverage_note=(
            f"Content-based metrics (markers, commented-out code, complexity) cover "
            f"{sampled_source} of {source_files} source files that were downloaded."
        ),
        methodology=METHODOLOGY,
    )
