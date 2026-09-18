"""Extract import statements from downloaded files and resolve them to repository files.

An edge is recorded only when an import resolves unambiguously to a file (or directory)
that exists in the tree. Unresolvable or ambiguous imports are counted, never guessed.
"""

import ast
import json
import posixpath
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.analyzers.file_classifier import detect_language

# fmt: off
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue",
                  ".svelte", ".json")
# fmt: on
_JS_IMPORT_RE = re.compile(
    r"""(?:import|export)\s[^'";]{0,500}?\sfrom\s*['"](?P<a>[^'"\n]{1,300})['"]"""
    r"""|\bimport\s*['"](?P<b>[^'"\n]{1,300})['"]"""
    r"""|\brequire\(\s*['"](?P<c>[^'"\n]{1,300})['"]\s*\)"""
    r"""|\bimport\(\s*['"](?P<d>[^'"\n]{1,300})['"]\s*\)"""
)
_GO_IMPORT_BLOCK_RE = re.compile(r"^import\s*\((?P<body>.*?)^\)", re.MULTILINE | re.DOTALL)
_GO_IMPORT_LINE_RE = re.compile(r'^\s*(?:[\w.]+\s+)?"(?P<path>[^"]+)"', re.MULTILINE)
_GO_SINGLE_RE = re.compile(r'^import\s+(?:[\w.]+\s+)?"(?P<path>[^"]+)"', re.MULTILINE)
_GO_MODULE_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_RUST_USE_RE = re.compile(r"\buse\s+crate::(?P<path>\w+(?:::\w+)*)")
_JVM_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?(?P<path>[\w.]+(?:\.\*)?)\s*;?", re.MULTILINE
)


@dataclass
class ImportStats:
    files_parsed: int = 0
    imports_found: int = 0
    internal_resolved: int = 0
    external: int = 0
    unresolved: int = 0


@dataclass
class ImportGraph:
    edges: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    stats: ImportStats = field(default_factory=ImportStats)
    languages: set[str] = field(default_factory=set)


class _Resolver:
    def __init__(self, paths: list[str], contents: dict[str, str]) -> None:
        self.paths = set(paths)
        self.dirs: set[str] = set()
        for p in paths:
            parent = posixpath.dirname(p)
            while parent and parent not in self.dirs:
                self.dirs.add(parent)
                parent = posixpath.dirname(parent)

        # Python: dotted suffix -> files
        self.py_index: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            if not p.endswith(".py"):
                continue
            parts = p[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.py_index[".".join(parts[i:])].append(p)

        # JVM: "com/x/Foo" suffix lookups by class file name
        self.jvm_by_name: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            if p.endswith((".java", ".kt", ".scala")):
                self.jvm_by_name[PurePosixPath(p).stem].append(p)

        # JS workspace packages: package name -> directory
        self.js_packages: dict[str, str] = {}
        self.ts_aliases: list[tuple[str, list[str], str]] = []  # (prefix, targets, base dir)
        for p, text in contents.items():
            name = PurePosixPath(p).name
            if name == "package.json":
                try:
                    data = json.loads(text)
                except (ValueError, RecursionError):
                    continue
                # Only nested workspace packages: the root package's name often equals a
                # published package that the repository's own tests import like a user would.
                if isinstance(data, dict) and isinstance(data.get("name"), str) and "/" in p:
                    self.js_packages[data["name"]] = posixpath.dirname(p)
            elif name in ("tsconfig.json", "jsconfig.json"):
                self._load_ts_paths(p, text)

        # Go modules: module path -> directory of go.mod
        self.go_modules: list[tuple[str, str]] = []
        for p, text in contents.items():
            if PurePosixPath(p).name == "go.mod":
                m = _GO_MODULE_RE.search(text)
                if m:
                    self.go_modules.append((m.group(1), posixpath.dirname(p)))
        self.go_modules.sort(key=lambda t: -len(t[0]))

    def _load_ts_paths(self, path: str, text: str) -> None:
        # tsconfig allows comments and trailing commas; strip the common forms.
        cleaned = re.sub(r"(?m)^\s*//[^\n]*$|/\*.*?\*/", "", text, flags=re.DOTALL)
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
        try:
            data = json.loads(cleaned)
        except (ValueError, RecursionError):
            return
        options = data.get("compilerOptions") if isinstance(data, dict) else None
        if not isinstance(options, dict) or not isinstance(options.get("paths"), dict):
            return
        base = posixpath.normpath(
            posixpath.join(posixpath.dirname(path), str(options.get("baseUrl", ".")))
        )
        for alias, targets in options["paths"].items():
            if isinstance(targets, list) and alias.endswith("*"):
                self.ts_aliases.append((alias[:-1], [str(t).rstrip("*") for t in targets], base))

    # --- JS/TS ---------------------------------------------------------------
    def _js_file(self, candidate: str) -> str | None:
        candidate = posixpath.normpath(candidate)
        if candidate.startswith("../") or candidate == "..":
            return None
        if candidate in self.paths:
            return candidate
        stem = re.sub(r"\.(js|jsx|mjs|cjs)$", "", candidate)  # TS ESM imports use .js
        for ext in _JS_EXTENSIONS:
            if stem + ext in self.paths:
                return stem + ext
        for ext in _JS_EXTENSIONS:
            if f"{candidate}/index{ext}" in self.paths:
                return f"{candidate}/index{ext}"
        return None

    def resolve_js(self, importer: str, spec: str) -> tuple[str, str | None]:
        spec = spec.split("?", 1)[0]
        if spec.startswith("."):
            target = self._js_file(posixpath.join(posixpath.dirname(importer), spec))
            return ("internal", target) if target else ("unresolved", None)
        for prefix, targets, base in self.ts_aliases:
            if prefix and spec.startswith(prefix):
                rest = spec[len(prefix) :]
                for t in targets:
                    target = self._js_file(posixpath.join(base, t, rest))
                    if target:
                        return "internal", target
                return "unresolved", None
        parts = spec.split("/")
        package = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
        if package in self.js_packages:
            root = self.js_packages[package]
            sub = spec[len(package) :].lstrip("/")
            target = None
            if sub:
                for base in (root, posixpath.join(root, "src")):
                    target = self._js_file(posixpath.join(base, sub))
                    if target:
                        break
            return "internal", target or (root if root else ".")
        return "external", None

    # --- Python ----------------------------------------------------------------
    def resolve_python(self, importer: str, module: str, level: int) -> tuple[str, str | None]:
        parts = module.split(".") if module else []
        if level > 0:
            base = posixpath.dirname(importer)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            for end in range(len(parts), -1, -1):
                joined = posixpath.normpath(posixpath.join(base, *parts[:end])) if end else base
                for candidate in (f"{joined}.py", f"{joined}/__init__.py"):
                    if candidate in self.paths:
                        return "internal", candidate
                if joined in self.dirs:
                    return "internal", joined  # namespace package
            return "unresolved", None
        if not parts or parts[0] in sys.stdlib_module_names:
            return "external", None
        for end in range(len(parts), 0, -1):
            matches = self.py_index.get(".".join(parts[:end]))
            if not matches:
                directory = "/".join(parts[:end])
                if directory in self.dirs:
                    return "internal", directory  # namespace package rooted at the repo root
                continue
            if len(matches) == 1:
                return "internal", matches[0]
            # Prefer a match rooted in the importer's top-level directory; otherwise ambiguous.
            top = importer.split("/", 1)[0]
            local = [m for m in matches if m.split("/", 1)[0] == top]
            if len(local) == 1:
                return "internal", local[0]
            return "unresolved", None
        return "external", None

    # --- Go / Rust / JVM ----------------------------------------------------------
    def resolve_go(self, spec: str) -> tuple[str, str | None]:
        for module, root in self.go_modules:
            if spec == module or spec.startswith(module + "/"):
                rel = spec[len(module) :].lstrip("/")
                target = posixpath.join(root, rel) if root else rel
                target = target or "."
                if target in self.dirs or target == ".":
                    return "internal", target
                return "unresolved", None
        return "external", None

    def resolve_rust(self, importer: str, path: str) -> tuple[str, str | None]:
        # crate root: the nearest ancestor 'src' directory
        parts = importer.split("/")
        if "src" not in parts:
            return "unresolved", None
        root = "/".join(parts[: len(parts) - parts[::-1].index("src")])
        segments = path.split("::")
        for end in range(len(segments), 0, -1):
            base = posixpath.join(root, *segments[:end])
            for candidate in (f"{base}.rs", f"{base}/mod.rs"):
                if candidate in self.paths:
                    return "internal", candidate
        return "unresolved", None

    def resolve_jvm(self, path: str) -> tuple[str, str | None]:
        if path.endswith(".*"):
            suffix = "/" + path[:-2].replace(".", "/")
            matches = [d for d in self.dirs if ("/" + d).endswith(suffix)]
        else:
            name = path.rsplit(".", 1)[-1]
            suffix = "/" + path.replace(".", "/")
            matches = [
                p
                for p in self.jvm_by_name.get(name, [])
                if ("/" + p.rsplit(".", 1)[0]).endswith(suffix)
            ]
        if len(matches) == 1:
            return "internal", matches[0]
        return ("unresolved", None) if matches else ("external", None)


def _python_imports(text: str) -> list[tuple[str, int]] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from pkg import name` may import a submodule (pkg.name) or an attribute of pkg.
            # Offer pkg.name first; the resolver falls back to the longest existing prefix.
            prefix = f"{node.module}." if node.module else ""
            for alias in node.names:
                if alias.name == "*":
                    found.append((node.module or "", node.level))
                else:
                    found.append((prefix + alias.name, node.level))
    return found


def build_import_graph(paths: list[str], contents: dict[str, str]) -> ImportGraph:
    resolver = _Resolver(paths, contents)
    graph = ImportGraph()
    stats = graph.stats

    def record(importer: str, outcome: tuple[str, str | None]) -> None:
        kind, target = outcome
        stats.imports_found += 1
        if kind == "internal" and target and target != importer:
            stats.internal_resolved += 1
            graph.edges[(importer, target)] += 1
        elif kind == "external":
            stats.external += 1
        elif kind == "unresolved":
            stats.unresolved += 1

    for path, text in contents.items():
        language = detect_language(path)
        if language == "Python":
            imports = _python_imports(text)
            if imports is None:
                continue
            for module, level in imports:
                record(path, resolver.resolve_python(path, module, level))
        elif language in ("JavaScript", "TypeScript", "Vue", "Svelte"):
            for m in _JS_IMPORT_RE.finditer(text):
                spec = next(g for g in m.groups() if g)
                record(path, resolver.resolve_js(path, spec))
        elif language == "Go":
            specs = [m.group("path") for m in _GO_SINGLE_RE.finditer(text)]
            for block in _GO_IMPORT_BLOCK_RE.finditer(text):
                specs += [m.group("path") for m in _GO_IMPORT_LINE_RE.finditer(block["body"])]
            for spec in specs:
                record(path, resolver.resolve_go(spec))
        elif language == "Rust":
            for m in _RUST_USE_RE.finditer(text):
                record(path, resolver.resolve_rust(path, m.group("path")))
        elif language in ("Java", "Kotlin", "Scala"):
            for m in _JVM_IMPORT_RE.finditer(text):
                record(path, resolver.resolve_jvm(m.group("path")))
        else:
            continue
        stats.files_parsed += 1
        graph.languages.add(language)
    return graph
