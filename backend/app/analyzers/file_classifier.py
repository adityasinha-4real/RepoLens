"""Classify repository paths: ignored/vendored directories, file category and language.

Everything here is a pure function of the path (and size), so results are deterministic
and never require downloading the file.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

# fmt: off
# Directories whose contents are generated, vendored or tool caches. They are counted but
# never analyzed. Matching is per path segment and case-sensitive, as on GitHub.
IGNORED_DIRS: frozenset[str] = frozenset({
    "node_modules", "bower_components", "jspm_packages", ".git", "dist", "build", "out", "target",
    "coverage", "htmlcov", ".nyc_output", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", "venv", ".venv", ".eggs", "site-packages", "vendor",
    "third_party", "Pods", "Carthage", ".gradle", ".next", ".nuxt", ".svelte-kit", ".turbo",
    ".parcel-cache", ".cache", ".terraform", ".serverless", ".vercel", ".angular", "obj",
    "DerivedData", ".dart_tool", ".pub-cache", "elm-stuff", "_build", "deps", ".stack-work",
})

# path segment -> language, for extensions that are ambiguous or absent
LANGUAGE_BY_FILENAME: dict[str, str] = {
    "Dockerfile": "Dockerfile", "Containerfile": "Dockerfile", "Makefile": "Makefile",
    "GNUmakefile": "Makefile", "CMakeLists.txt": "CMake", "Rakefile": "Ruby", "Gemfile": "Ruby",
    "Vagrantfile": "Ruby", "Jenkinsfile": "Groovy", "BUILD": "Starlark", "BUILD.bazel": "Starlark",
    "WORKSPACE": "Starlark", "Justfile": "Just", "justfile": "Just",
}

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "Python", ".pyi": "Python", ".pyx": "Cython", ".ipynb": "Jupyter Notebook",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript", ".tsx": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".groovy": "Groovy",
    ".gradle": "Groovy", ".clj": "Clojure", ".cljs": "Clojure",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".hpp": "C++", ".hh": "C++", ".hxx": "C++", ".m": "Objective-C", ".mm": "Objective-C++",
    ".cs": "C#", ".fs": "F#", ".vb": "Visual Basic", ".swift": "Swift", ".dart": "Dart",
    ".rb": "Ruby", ".php": "PHP", ".pl": "Perl", ".pm": "Perl", ".lua": "Lua", ".r": "R",
    ".R": "R", ".jl": "Julia", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".hs": "Haskell", ".ml": "OCaml", ".mli": "OCaml", ".elm": "Elm", ".zig": "Zig",
    ".nim": "Nim", ".v": "V", ".sol": "Solidity", ".cr": "Crystal", ".d": "D",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell", ".ps1": "PowerShell",
    ".bat": "Batchfile", ".cmd": "Batchfile",
    ".sql": "SQL", ".graphql": "GraphQL", ".gql": "GraphQL", ".proto": "Protocol Buffers",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "Sass",
    ".less": "Less", ".styl": "Stylus",
    ".tf": "HCL", ".hcl": "HCL", ".nix": "Nix", ".cmake": "CMake", ".mk": "Makefile",
    ".asm": "Assembly", ".s": "Assembly", ".wasm": "WebAssembly", ".wat": "WebAssembly",
    ".md": "Markdown", ".mdx": "MDX", ".rst": "reStructuredText", ".adoc": "AsciiDoc",
    ".tex": "TeX",
    ".json": "JSON", ".jsonc": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".ini": "INI", ".cfg": "INI", ".csv": "CSV",
}

# Languages that are markup, prose or data rather than executable source code.
NON_CODE_LANGUAGES: frozenset[str] = frozenset({
    "Markdown", "MDX", "reStructuredText", "AsciiDoc", "TeX", "JSON", "YAML", "TOML", "XML",
    "INI", "CSV", "Jupyter Notebook",
})

BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".avif", ".tiff", ".psd",
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".mov", ".avi", ".mkv", ".webm",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war", ".whl",
    ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".obj", ".lib", ".class", ".pyc", ".pyo",
    ".bin", ".dat", ".db", ".sqlite", ".sqlite3", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".keystore", ".jks", ".p12", ".pfx", ".der", ".onnx", ".pt", ".pth",
    ".h5", ".pkl", ".parquet", ".npy", ".npz", ".tflite", ".dmg", ".iso", ".apk", ".ipa",
})
ASSET_EXTENSIONS: frozenset[str] = frozenset({".svg"}) | {
    e for e in BINARY_EXTENSIONS
    if e in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".avif", ".mp3", ".mp4",
             ".wav", ".ogg", ".mov", ".webm", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".psd"}
}

LOCKFILES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "Cargo.lock",
    "poetry.lock", "Pipfile.lock", "uv.lock", "pdm.lock", "composer.lock", "Gemfile.lock",
    "go.sum", "mix.lock", "pubspec.lock", "Podfile.lock", "flake.lock", "gradle.lockfile",
    "packages.lock.json", "npm-shrinkwrap.json",
})

DOC_NAMES: frozenset[str] = frozenset({
    "readme", "contributing", "changelog", "changes", "history", "license", "licence", "copying",
    "code_of_conduct", "security", "authors", "maintainers", "support", "governance", "notice",
})
DOC_DIRS: frozenset[str] = frozenset({"docs", "doc", "documentation", "wiki", "man"})

CONFIG_FILENAMES: frozenset[str] = frozenset({
    ".gitignore", ".gitattributes", ".editorconfig", ".dockerignore", ".npmrc", ".nvmrc",
    ".prettierrc", ".eslintrc", ".babelrc", ".browserslistrc", ".env.example", ".env.sample",
    ".pre-commit-config.yaml", ".python-version", ".ruby-version", ".tool-versions",
    "Dockerfile", "Containerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
    "compose.yaml", "Makefile", "Procfile", "tsconfig.json", "setup.cfg", "tox.ini",
    "pytest.ini", "mypy.ini", ".flake8", ".pylintrc", "ruff.toml", ".ruff.toml", "biome.json",
    "renovate.json", "netlify.toml", "vercel.json", "fly.toml", "render.yaml", "app.json",
})
CONFIG_EXTENSIONS: frozenset[str] = frozenset({
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env",
})

TEST_DIR_NAMES: frozenset[str] = frozenset({
    "test", "tests", "__tests__", "spec", "specs", "testing", "e2e", "integration-tests",
    "test-utils", "cypress", "playwright",
})

# fmt: on


class FileCategory(StrEnum):
    SOURCE = "source"
    TEST = "test"
    DOCUMENTATION = "documentation"
    CONFIG = "config"
    DATA = "data"
    ASSET = "asset"
    BINARY = "binary"
    LOCKFILE = "lockfile"
    GENERATED = "generated"
    OTHER = "other"


@dataclass(frozen=True)
class FileClass:
    category: FileCategory
    language: str | None


_AUXILIARY_DIR_RE = re.compile(
    r"(^|/)(examples?|samples?|demos?|fixtures?|__fixtures__|testdata|test-fixtures|tests?|"
    r"__tests__|e2e|bench|benchmarks?|playground|templates?|docs?)/",
    re.IGNORECASE,
)


def is_auxiliary_path(path: str) -> bool:
    """True for paths inside examples, fixtures, tests, benchmarks, templates or docs:
    code that ships with a repository but is not its main product."""
    return bool(_AUXILIARY_DIR_RE.search(path))


# Generic build-output names are only treated as output outside source trees:
# `dist/` at a package root is an artifact, `src/build/` is source code.
OUTPUT_DIR_NAMES: frozenset[str] = frozenset({"build", "dist", "out", "target", "obj", "_build"})
SOURCE_ROOT_NAMES: frozenset[str] = frozenset({"src", "lib", "source", "sources"})


def ignored_index(segments: list[str]) -> int | None:
    """Index of the first ignored directory among `segments` (directory names only)."""
    inside_source = False
    for i, segment in enumerate(segments):
        if segment in IGNORED_DIRS and not (inside_source and segment in OUTPUT_DIR_NAMES):
            return i
        if segment in SOURCE_ROOT_NAMES:
            inside_source = True
    return None


def ignored_segment(path: str) -> str | None:
    """Return the first ignored directory segment in `path`, if any.

    Only directory segments count: a *file* called `build` is not ignored.
    """
    segments = path.split("/")[:-1]
    index = ignored_index(segments)
    return segments[index] if index is not None else None


def detect_language(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.name in LANGUAGE_BY_FILENAME:
        return LANGUAGE_BY_FILENAME[p.name]
    if p.name.startswith("Dockerfile.") or p.name.endswith(".dockerfile"):
        return "Dockerfile"
    return LANGUAGE_BY_EXTENSION.get(p.suffix) or LANGUAGE_BY_EXTENSION.get(p.suffix.lower())


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    parts = [s.lower() for s in p.parts[:-1]]
    if any(part in TEST_DIR_NAMES for part in parts):
        return True
    name = p.name.lower()
    stem = name.split(".", 1)[0]
    return (
        stem.startswith("test_")
        or stem.endswith(("_test", "_spec"))
        or ".test." in name
        or ".spec." in name
        or (p.suffix == ".java" and p.stem.endswith(("Test", "Tests", "IT")))
        or (p.suffix in {".cs", ".kt", ".swift"} and p.stem.endswith(("Test", "Tests")))
    )


def is_generated_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.endswith(
        (
            ".min.js",
            ".min.css",
            ".map",
            ".bundle.js",
            ".pb.go",
            "_pb2.py",
            ".generated.ts",
            ".g.dart",
            ".freezed.dart",
            ".designer.cs",
        )
    ) or name.startswith("generated_")


def classify(path: str) -> FileClass:
    p = PurePosixPath(path)
    name = p.name
    lower_name = name.lower()
    suffix = p.suffix.lower()
    language = detect_language(path)

    if name in LOCKFILES:
        return FileClass(FileCategory.LOCKFILE, language)
    if suffix in ASSET_EXTENSIONS:
        return FileClass(FileCategory.ASSET, None)
    if suffix in BINARY_EXTENSIONS:
        return FileClass(FileCategory.BINARY, None)
    if is_generated_path(path):
        return FileClass(FileCategory.GENERATED, language)

    stem = lower_name.split(".", 1)[0]
    in_doc_dir = any(s.lower() in DOC_DIRS for s in p.parts[:-1])
    if stem in DOC_NAMES or (in_doc_dir and suffix in {".md", ".mdx", ".rst", ".adoc", ".txt"}):
        return FileClass(FileCategory.DOCUMENTATION, language)
    if suffix in {".md", ".mdx", ".rst", ".adoc", ".txt"}:
        return FileClass(FileCategory.DOCUMENTATION, language)

    if language and language not in NON_CODE_LANGUAGES:
        if is_test_path(path):
            return FileClass(FileCategory.TEST, language)
        if (
            name in CONFIG_FILENAMES
            or language in {"Dockerfile", "Makefile"}
            or ".config." in lower_name
            or lower_name.startswith((".eslintrc", ".prettierrc", ".stylelintrc", ".babelrc"))
        ):
            return FileClass(FileCategory.CONFIG, language)
        return FileClass(FileCategory.SOURCE, language)

    if (
        name in CONFIG_FILENAMES
        or suffix in CONFIG_EXTENSIONS
        or lower_name.startswith((".eslintrc", ".prettierrc", ".stylelintrc", ".babelrc"))
        or (p.parts and p.parts[0] == ".github")
    ):
        return FileClass(FileCategory.CONFIG, language)
    if suffix in {".json", ".csv", ".tsv", ".xml", ".jsonl", ".ndjson", ".geojson"}:
        return FileClass(FileCategory.DATA, language)
    return FileClass(FileCategory.OTHER, language)
