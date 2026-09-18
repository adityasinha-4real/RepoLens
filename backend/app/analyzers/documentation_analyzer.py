"""Documentation presence and measurable README / docs indicators."""

import ast
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from app.analyzers.file_classifier import FileCategory, classify, ignored_segment
from app.analyzers.line_counter import count_lines
from app.schemas.documentation import (
    DirectoryInfo,
    DocstringCoverage,
    DocumentationAnalysis,
    PresenceCheck,
    ReadmeInfo,
)
from app.services.repository_tree import RepositoryTree

WORDS_PER_MINUTE = 200

# fmt: off
# (key, label, heading keywords)
README_SECTIONS: list[tuple[str, str, tuple[str, ...]]] = [
    ("install", "Installation / setup",
     ("install", "setup", "set up", "getting started", "quick start", "quickstart")),
    ("usage", "Usage / examples", ("usage", "example", "how to use", "tutorial", "demo")),
    ("configuration", "Configuration", ("config", "environment", "settings", "options")),
    ("features", "Features / overview", ("feature", "overview", "about", "introduction",
                                         "what is", "why")),
    ("requirements", "Requirements", ("requirement", "prerequisite", "dependencies")),
    ("testing", "Testing", ("test", "testing")),
    ("api", "API / reference", ("api", "reference", "documentation", "docs")),
    ("deployment", "Deployment", ("deploy", "production", "hosting")),
    ("contributing", "Contributing", ("contribut", "development", "developing")),
    ("license", "License", ("license", "licence")),
    ("support", "Support / FAQ", ("support", "faq", "troubleshoot", "help", "community")),
]

COMMUNITY_FILES: list[tuple[str, str, tuple[str, ...]]] = [
    ("contributing", "Contributing guide", ("contributing",)),
    ("license", "License file", ("license", "licence", "copying")),
    ("changelog", "Changelog", ("changelog", "changes", "history", "news", "releases")),
    ("code_of_conduct", "Code of conduct", ("code_of_conduct", "code-of-conduct")),
    ("security", "Security policy", ("security",)),
    ("support", "Support guide", ("support",)),
    ("citation", "Citation file", ("citation",)),
    ("authors", "Authors / maintainers", ("authors", "maintainers", "contributors")),
]
_SITE_GENERATORS = [
    ("mkdocs.yml", "MkDocs"), ("mkdocs.yaml", "MkDocs"),
    ("docusaurus.config.js", "Docusaurus"), ("docusaurus.config.ts", "Docusaurus"),
    ("book.toml", "mdBook"), (".readthedocs.yaml", "Read the Docs"),
    (".readthedocs.yml", "Read the Docs"), ("antora.yml", "Antora"), ("_config.yml", "Jekyll"),
    (".vitepress/config.ts", "VitePress"), (".vitepress/config.js", "VitePress"),
    ("astro.config.mjs", "Astro/Starlight"), ("conf.py", "Sphinx"),
]
# fmt: on
_DOCS_DIRS = ("docs", "doc", "documentation", "website/docs")
_EXAMPLE_DIRS = ("examples", "example", "samples", "sample", "demo", "demos")

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_LINK = re.compile(r"(!?)\[([^\[\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_HTML_IMG = re.compile(r"<img\s[^>]*src=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HTML_LINK = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"']", re.IGNORECASE)
_RST_UNDERLINE = re.compile(r"^([=\-~^\"'`#*+])\1{2,}\s*$")
_BADGE_HOSTS = (
    "shields.io",
    "badge",
    "travis-ci",
    "codecov.io",
    "circleci.com/gh",
    "github.com/.*/workflows/",
    "/actions/workflows/",
    "badgen.net",
    "pepy.tech",
)


def _find_readme(paths: set[str]) -> str | None:
    def candidates(prefix: str) -> list[str]:
        return sorted(
            p
            for p in paths
            if p.startswith(prefix)
            and "/" not in p[len(prefix) :]
            and PurePosixPath(p).name.lower().split(".")[0] == "readme"
        )

    for prefix in ("", ".github/", "docs/"):
        found = candidates(prefix)
        if found:
            # Prefer Markdown, then reStructuredText, then anything else.
            found.sort(
                key=lambda p: (
                    not p.lower().endswith((".md", ".markdown")),
                    not p.lower().endswith(".rst"),
                    p,
                )
            )
            return found[0]
    return None


def _strip_code_blocks(text: str) -> tuple[str, int]:
    blocks = 0
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            if not in_fence:
                blocks += 1
            in_fence = not in_fence
            continue
        if not in_fence:
            out_lines.append(line)
    return "\n".join(out_lines), blocks


def _is_badge(url: str) -> bool:
    return any(re.search(h, url) for h in _BADGE_HOSTS)


def _link_target_exists(target: str, readme_path: str, paths: set[str], dirs: set[str]) -> bool:
    """Resolve a relative link the way GitHub does ('/' is the repository root)."""
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/") or ".")
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(readme_path), target))
    if resolved == ".":
        return True
    if resolved.startswith("../") or resolved == "..":
        return False  # escapes the repository
    return resolved in paths or resolved in dirs


def analyze_readme(path: str, text: str, paths: set[str], dirs: set[str]) -> ReadmeInfo:
    lower = path.lower()
    fmt = (
        "markdown"
        if lower.endswith((".md", ".markdown", ".mdx"))
        else ("rst" if lower.endswith(".rst") else "text")
    )
    prose, code_blocks = _strip_code_blocks(text) if fmt == "markdown" else (text, 0)
    if fmt == "rst":
        code_blocks = len(re.findall(r"^\.\. code(?:-block)?::|::\s*$", text, re.MULTILINE))

    headings: list[str] = []
    lines = prose.splitlines()
    for i, line in enumerate(lines):
        if fmt == "markdown":
            m = _MD_HEADING.match(line)
            if m:
                headings.append(
                    re.sub(r"[*_`]|<[^>]+>|!\[[^\]]*\]\([^)]*\)", "", m.group(2)).strip()
                )
            elif i > 0 and re.fullmatch(r"(=+|-+)\s*", line) and lines[i - 1].strip():
                headings.append(lines[i - 1].strip())  # setext heading
        elif fmt == "rst" and i > 0 and _RST_UNDERLINE.match(line) and lines[i - 1].strip():
            headings.append(lines[i - 1].strip())
    headings = [h for h in headings if h][:40]

    lowered = [h.lower() for h in headings]
    sections = [
        PresenceCheck(key=key, label=label, present=any(k in h for h in lowered for k in keywords))
        for key, label, keywords in README_SECTIONS
    ]

    links = images = badges = 0
    broken: list[str] = []
    targets: list[tuple[bool, str]] = [
        (m.group(1) == "!", m.group(3)) for m in _MD_LINK.finditer(prose)
    ]
    targets += [(True, u) for u in _HTML_IMG.findall(prose)]
    targets += [(False, u) for u in _HTML_LINK.findall(prose)]
    for is_image, url in targets:
        if is_image:
            images += 1
            if _is_badge(url):
                badges += 1
        else:
            links += 1
        parts = urlsplit(url)
        if parts.scheme or url.startswith(("#", "//", "mailto:")) or not parts.path:
            continue
        target = unquote(parts.path)
        if not _link_target_exists(target, path, paths, dirs) and target not in broken:
            broken.append(target)

    words = len(re.findall(r"[A-Za-z0-9][\w'-]*", prose))
    return ReadmeInfo(
        path=path,
        format=fmt,
        bytes=len(text.encode()),
        words=words,
        lines=text.count("\n") + 1,
        reading_minutes=round(words / WORDS_PER_MINUTE, 1),
        headings=headings,
        sections=sections,
        code_blocks=code_blocks,
        links=links,
        images=images,
        badges=badges,
        has_table_of_contents=any(h in ("table of contents", "contents", "toc") for h in lowered),
        broken_relative_links=broken[:30],
    )


def python_docstring_coverage(contents: dict[str, str]) -> DocstringCoverage | None:
    public = documented = files = 0
    for path, text in contents.items():
        cls = classify(path)
        if cls.language != "Python" or cls.category != FileCategory.SOURCE:
            continue
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        files += 1
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and not node.name.startswith("_"):
                public += 1
                if ast.get_docstring(node):
                    documented += 1
    if not public:
        return None
    return DocstringCoverage(
        public_definitions=public,
        documented=documented,
        percent=round(100 * documented / public, 1),
        files_analyzed=files,
    )


def _directory_info(
    candidates: tuple[str, ...], dirs: set[str], file_paths: list[str], with_docs: bool
) -> DirectoryInfo | None:
    for d in candidates:
        if d in dirs:
            inside = [p for p in file_paths if p.startswith(d + "/")]
            info = DirectoryInfo(path=d, files=len(inside))
            if with_docs:
                info.doc_files = sum(
                    classify(p).category == FileCategory.DOCUMENTATION for p in inside
                )
            return info
    return None


def analyze_documentation(
    tree: RepositoryTree,
    contents: dict[str, str],
    license_spdx: str | None,
    license_name: str | None,
) -> DocumentationAnalysis:
    file_paths = [e.path for e in tree.files() if ignored_segment(e.path) is None]
    # Root-level symlinks (e.g. README.md -> packages/x/README.md) count as documents too.
    root_links = [e.path for e in tree.entries if e.type == "symlink" and "/" not in e.path]
    paths = set(file_paths) | set(root_links)
    dirs = {e.path for e in tree.entries if e.type == "dir"}
    for p in file_paths:  # trees can be truncated; derive parent directories too
        parent = posixpath.dirname(p)
        while parent and parent not in dirs:
            dirs.add(parent)
            parent = posixpath.dirname(parent)
    notes: list[str] = []

    readme_path = _find_readme(paths)
    readme = None
    if readme_path:
        text = contents.get(readme_path)
        if text is None:
            notes.append(f"{readme_path} exists but was not downloaded (size limit).")
        else:
            readme = analyze_readme(readme_path, text, paths, dirs)

    top_level = [
        p
        for p in file_paths + root_links
        if p.count("/") == 0 or (p.startswith((".github/", "docs/")) and p.count("/") == 1)
    ]
    files: list[PresenceCheck] = []
    license_file = None
    for key, label, stems in COMMUNITY_FILES:
        match = sorted(
            (p for p in top_level if PurePosixPath(p).name.lower().split(".")[0] in stems),
            key=lambda p: (p.count("/"), p),
        )
        found = match[0] if match else None
        if key == "license":
            license_file = found
        files.append(PresenceCheck(key=key, label=label, present=found is not None, path=found))
    issue_templates = next(
        (
            p
            for p in sorted(paths)
            if p.startswith(".github/ISSUE_TEMPLATE") or p.lower() == ".github/issue_template.md"
        ),
        None,
    )
    pr_template = next(
        (p for p in sorted(paths) if PurePosixPath(p).name.lower() == "pull_request_template.md"),
        None,
    )
    files.append(
        PresenceCheck(
            key="issue_templates",
            label="Issue templates",
            present=issue_templates is not None,
            path=issue_templates,
        )
    )
    files.append(
        PresenceCheck(
            key="pr_template",
            label="Pull request template",
            present=pr_template is not None,
            path=pr_template,
        )
    )

    docs_dir = _directory_info(_DOCS_DIRS, dirs, file_paths, with_docs=True)
    if docs_dir:
        for filename, generator in _SITE_GENERATORS:
            if filename in paths or f"{docs_dir.path}/{filename}" in paths:
                docs_dir.site_generator = generator
                break

    code_total = comment_total = 0
    for p, text in contents.items():
        cls = classify(p)
        if cls.category == FileCategory.SOURCE:
            counts = count_lines(text, cls.language)
            code_total += counts.code
            comment_total += counts.comment
    density = (
        round(comment_total / (code_total + comment_total), 3)
        if code_total + comment_total
        else None
    )

    return DocumentationAnalysis(
        readme=readme,
        files=files,
        license_spdx=license_spdx,
        license_name=license_name,
        license_file=license_file,
        docs_directory=docs_dir,
        examples_directory=_directory_info(_EXAMPLE_DIRS, dirs, file_paths, with_docs=False),
        comment_density=density,
        python_docstrings=python_docstring_coverage(contents),
        notes=notes,
    )
