"""Parsers for dependency manifests. Each parser is static: manifests are never executed.

Every parser takes the file text and returns a list of ParsedDependency. It raises
ManifestParseError when the file is malformed.
"""

import configparser
import json
import re
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from defusedxml import ElementTree as SafeET  # hardened against XXE / entity expansion
from defusedxml.common import DefusedXmlException

Scope = str  # "production" | "development" | "optional" | "peer" | "build"


class ManifestParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDependency:
    name: str
    version: str | None
    scope: Scope
    source: str = "registry"  # registry | git | path | url
    direct: bool = True


# --- helpers -----------------------------------------------------------------

_PEP508_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?P<spec>[^;#]*)"
)
_DEV_HINT_RE = re.compile(
    r"(^|[-_.])(dev|develop|development|test|tests|testing|lint|docs?|ci|typing)"
    r"([-_.]|$)",
    re.IGNORECASE,
)


def _is_dev_name(name: str) -> bool:
    return bool(_DEV_HINT_RE.search(name))


def _pep508(requirement: str, scope: Scope) -> ParsedDependency | None:
    req = requirement.strip()
    if not req or req.startswith("#"):
        return None
    if " @ " in req:
        name, _, target = req.partition(" @ ")
        source = "git" if target.strip().startswith("git+") else "url"
        m = _PEP508_RE.match(name)
        return ParsedDependency(m.group("name") if m else name.strip(), None, scope, source)
    m = _PEP508_RE.match(req)
    if not m:
        return None
    spec = m.group("spec").strip() or None
    return ParsedDependency(m.group("name"), spec, scope)


def _load_toml(text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError) as exc:
        raise ManifestParseError(f"invalid TOML: {exc}") from exc


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ManifestParseError(f"invalid JSON: {exc.__class__.__name__}") from exc


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# --- JavaScript ----------------------------------------------------------------

_NPM_SECTIONS = {
    "dependencies": "production",
    "devDependencies": "development",
    "peerDependencies": "peer",
    "optionalDependencies": "optional",
}


def _npm_source(spec: str) -> str:
    if spec.startswith(("git+", "git:", "github:", "gitlab:", "bitbucket:")) or re.match(
        r"^[\w.-]+/[\w.-]+(#.*)?$", spec
    ):
        return "git"
    if spec.startswith(("file:", "link:", "portal:")):
        return "path"
    if spec.startswith(("http://", "https://")):
        return "url"
    return "registry"


def parse_package_json(text: str) -> list[ParsedDependency]:
    data = _load_json(text)
    if not isinstance(data, dict):
        raise ManifestParseError("package.json must contain an object")
    deps: list[ParsedDependency] = []
    for section, scope in _NPM_SECTIONS.items():
        for name, spec in _as_dict(data.get(section)).items():
            spec_s = spec if isinstance(spec, str) else None
            deps.append(
                ParsedDependency(
                    str(name), spec_s, scope, _npm_source(spec_s) if spec_s else "registry"
                )
            )
    return deps


# --- Python --------------------------------------------------------------------


def parse_requirements(text: str, path: str) -> list[ParsedDependency]:
    scope = (
        "development"
        if _is_dev_name(PurePosixPath(path).name) or _is_dev_name(PurePosixPath(path).parent.name)
        else "production"
    )
    deps: list[ParsedDependency] = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(
            (
                "-r",
                "-c",
                "--requirement",
                "--constraint",
                "--index-url",
                "--extra-index-url",
                "-i ",
                "--find-links",
                "-f ",
                "--hash",
                "--trusted-host",
                "--pre",
                "--no-binary",
                "--only-binary",
            )
        ):
            continue
        if line.startswith(("-e ", "--editable")):
            target = line.split(None, 1)[-1]
            name_match = re.search(r"#egg=([\w.-]+)", target)
            deps.append(
                ParsedDependency(
                    name_match.group(1) if name_match else target,
                    None,
                    scope,
                    "git" if target.startswith("git+") else "path",
                )
            )
            continue
        if line.startswith(("git+", "http://", "https://")):
            name_match = re.search(r"#egg=([\w.-]+)", line)
            deps.append(
                ParsedDependency(
                    name_match.group(1) if name_match else line,
                    None,
                    scope,
                    "git" if line.startswith("git+") else "url",
                )
            )
            continue
        dep = _pep508(line.split(" --hash", 1)[0], scope)
        if dep:
            deps.append(dep)
    return deps


def _poetry_deps(table: Any, scope: Scope) -> Iterable[ParsedDependency]:
    for name, spec in _as_dict(table).items():
        if name.lower() == "python":
            continue
        if isinstance(spec, str):
            yield ParsedDependency(name, spec, scope)
        elif isinstance(spec, dict):
            source = (
                "git"
                if "git" in spec
                else "path"
                if "path" in spec
                else ("url" if "url" in spec else "registry")
            )
            dep_scope = "optional" if spec.get("optional") and scope == "production" else scope
            version = spec.get("version")
            yield ParsedDependency(
                name, version if isinstance(version, str) else None, dep_scope, source
            )


def parse_pyproject(text: str) -> list[ParsedDependency]:
    data = _load_toml(text)
    deps: list[ParsedDependency] = []
    project = _as_dict(data.get("project"))
    for req in project.get("dependencies") or []:
        if isinstance(req, str) and (dep := _pep508(req, "production")):
            deps.append(dep)
    for group, reqs in _as_dict(project.get("optional-dependencies")).items():
        scope = "development" if _is_dev_name(group) else "optional"
        for req in reqs if isinstance(reqs, list) else []:
            if isinstance(req, str) and (dep := _pep508(req, scope)):
                deps.append(dep)
    # PEP 735 dependency groups (also used by uv)
    for reqs in _as_dict(data.get("dependency-groups")).values():
        for req in reqs if isinstance(reqs, list) else []:
            if isinstance(req, str) and (dep := _pep508(req, "development")):
                deps.append(dep)

    tool = _as_dict(data.get("tool"))
    poetry = _as_dict(tool.get("poetry"))
    deps += _poetry_deps(poetry.get("dependencies"), "production")
    deps += _poetry_deps(poetry.get("dev-dependencies"), "development")
    for group_name, group in _as_dict(poetry.get("group")).items():
        scope = "development" if group_name != "main" else "production"
        deps += _poetry_deps(_as_dict(group).get("dependencies"), scope)
    for source in (
        _as_dict(tool.get("uv")).get("dev-dependencies"),
        *_as_dict(_as_dict(tool.get("pdm")).get("dev-dependencies")).values(),
    ):
        for req in source if isinstance(source, list) else []:
            if isinstance(req, str) and (dep := _pep508(req, "development")):
                deps.append(dep)
    return deps


def parse_pipfile(text: str) -> list[ParsedDependency]:
    data = _load_toml(text)
    return [
        *_poetry_deps(data.get("packages"), "production"),
        *_poetry_deps(data.get("dev-packages"), "development"),
    ]


def parse_setup_cfg(text: str) -> list[ParsedDependency]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ManifestParseError(f"invalid setup.cfg: {exc.__class__.__name__}") from exc
    deps: list[ParsedDependency] = []
    if parser.has_option("options", "install_requires"):
        for line in parser.get("options", "install_requires").splitlines():
            if dep := _pep508(line, "production"):
                deps.append(dep)
    if parser.has_section("options.extras_require"):
        for group, value in parser.items("options.extras_require"):
            scope = "development" if _is_dev_name(group) else "optional"
            for line in value.splitlines():
                if dep := _pep508(line, scope):
                    deps.append(dep)
    return deps


# --- JVM -----------------------------------------------------------------------


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: Any, name: str) -> str | None:
    for child in el:
        if _strip_ns(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def parse_pom(text: str) -> list[ParsedDependency]:
    try:
        root = SafeET.fromstring(text)
    except (SafeET.ParseError, DefusedXmlException, ValueError) as exc:
        raise ManifestParseError(f"invalid XML: {exc.__class__.__name__}") from exc

    properties: dict[str, str] = {}
    for el in root:
        if _strip_ns(el.tag) == "properties":
            for prop in el:
                if prop.text:
                    properties[_strip_ns(prop.tag)] = prop.text.strip()
    project_version = _child_text(root, "version")
    if project_version:
        properties.setdefault("project.version", project_version)

    def resolve(value: str | None) -> str | None:
        if value is None:
            return None
        return re.sub(r"\$\{([^}]+)\}", lambda m: properties.get(m.group(1), m.group(0)), value)

    deps: list[ParsedDependency] = []
    for section in root:
        # Only <project><dependencies>; <dependencyManagement> holds constraints, not deps.
        if _strip_ns(section.tag) != "dependencies":
            continue
        for dep in section:
            if _strip_ns(dep.tag) != "dependency":
                continue
            group, artifact = _child_text(dep, "groupId"), _child_text(dep, "artifactId")
            if not artifact:
                continue
            scope_raw = (_child_text(dep, "scope") or "compile").lower()
            scope = {"test": "development", "provided": "build", "system": "build"}.get(
                scope_raw, "production"
            )
            if (_child_text(dep, "optional") or "").lower() == "true":
                scope = "optional"
            name = f"{resolve(group)}:{artifact}" if group else artifact
            deps.append(ParsedDependency(name, resolve(_child_text(dep, "version")), scope))
    return deps


_GRADLE_CONFIGS = {
    "implementation": "production",
    "api": "production",
    "compile": "production",
    "runtimeOnly": "production",
    "runtime": "production",
    "compileOnly": "build",
    "annotationProcessor": "build",
    "kapt": "build",
    "ksp": "build",
    "testImplementation": "development",
    "testCompileOnly": "development",
    "testRuntimeOnly": "development",
    "androidTestImplementation": "development",
    "debugImplementation": "development",
    "testCompile": "development",
}
_GRADLE_STRING_RE = re.compile(
    r"\b(?P<config>" + "|".join(_GRADLE_CONFIGS) + r")\b\s*\(?\s*(?:platform\s*\(\s*)?"
    r"[\"'](?P<coord>[^\"'$\s]+(?:\$\{?[\w.]+\}?[^\"'\s]*)?)[\"']"
)
_GRADLE_MAP_RE = re.compile(
    r"\b(?P<config>" + "|".join(_GRADLE_CONFIGS) + r")\b\s*\(?\s*group\s*[:=]\s*[\"'](?P<g>[^\"']+)"
    r"[\"']\s*,\s*name\s*[:=]\s*[\"'](?P<n>[^\"']+)[\"']"
    r"(?:\s*,\s*version\s*[:=]\s*[\"'](?P<v>[^\"']+)[\"'])?"
)


def parse_gradle(text: str) -> list[ParsedDependency]:
    """Parse string and map notations. Version-catalog aliases (libs.x) cannot be resolved
    statically without the catalog, so they are not reported."""
    deps: list[ParsedDependency] = []
    for m in _GRADLE_STRING_RE.finditer(text):
        parts = m.group("coord").split(":")
        if len(parts) < 2:
            continue
        version = parts[2] if len(parts) > 2 and parts[2] else None
        deps.append(
            ParsedDependency(f"{parts[0]}:{parts[1]}", version, _GRADLE_CONFIGS[m.group("config")])
        )
    for m in _GRADLE_MAP_RE.finditer(text):
        deps.append(
            ParsedDependency(
                f"{m.group('g')}:{m.group('n')}", m.group("v"), _GRADLE_CONFIGS[m.group("config")]
            )
        )
    return deps


# --- Rust / Go / PHP / Ruby ------------------------------------------------------


def _cargo_table(table: Any, scope: Scope) -> Iterable[ParsedDependency]:
    for name, spec in _as_dict(table).items():
        if isinstance(spec, str):
            yield ParsedDependency(name, spec, scope)
        elif isinstance(spec, dict):
            if spec.get("workspace") is True:
                yield ParsedDependency(name, None, scope, "workspace")
                continue
            source = "git" if "git" in spec else "path" if "path" in spec else "registry"
            dep_scope = "optional" if spec.get("optional") and scope == "production" else scope
            version = spec.get("version")
            yield ParsedDependency(
                str(spec.get("package", name)),
                version if isinstance(version, str) else None,
                dep_scope,
                source,
            )


def parse_cargo(text: str) -> list[ParsedDependency]:
    data = _load_toml(text)
    deps = [
        *_cargo_table(data.get("dependencies"), "production"),
        *_cargo_table(data.get("dev-dependencies"), "development"),
        *_cargo_table(data.get("build-dependencies"), "build"),
    ]
    for target in _as_dict(data.get("target")).values():
        target = _as_dict(target)
        deps += _cargo_table(target.get("dependencies"), "production")
        deps += _cargo_table(target.get("dev-dependencies"), "development")
    deps += _cargo_table(_as_dict(data.get("workspace")).get("dependencies"), "production")
    return deps


_GO_REQUIRE_LINE = re.compile(r"^\s*(?P<mod>[^\s()]+)\s+(?P<ver>v[^\s]+)(?P<rest>.*)$")


def parse_go_mod(text: str) -> list[ParsedDependency]:
    deps: list[ParsedDependency] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require "):
            line = line[len("require ") :]
        elif not in_block:
            continue
        m = _GO_REQUIRE_LINE.match(line)
        if m:
            deps.append(
                ParsedDependency(
                    m.group("mod"),
                    m.group("ver"),
                    "production",
                    direct="// indirect" not in m.group("rest"),
                )
            )
    return deps


def parse_composer(text: str) -> list[ParsedDependency]:
    data = _load_json(text)
    if not isinstance(data, dict):
        raise ManifestParseError("composer.json must contain an object")
    deps: list[ParsedDependency] = []
    for section, scope in (("require", "production"), ("require-dev", "development")):
        for name, spec in _as_dict(data.get(section)).items():
            # Platform requirements (php, ext-*, lib-*) are not packages.
            if name == "php" or name.startswith(("ext-", "lib-")) or "/" not in name:
                continue
            deps.append(ParsedDependency(name, spec if isinstance(spec, str) else None, scope))
    return deps


_GEM_RE = re.compile(r"""^\s*gem\s+['"](?P<name>[^'"]+)['"](?P<rest>.*)$""")
_GEM_VERSION_RE = re.compile(r"""['"]\s*([~<>=!]*\s*\d[^'"]*)['"]""")
_GROUP_RE = re.compile(r"^\s*group\s+(?P<groups>.+?)\s+do\s*$")


def parse_gemfile(text: str) -> list[ParsedDependency]:
    deps: list[ParsedDependency] = []
    group_stack: list[bool] = []  # True when the enclosing group is dev/test-only
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if g := _GROUP_RE.match(line):
            groups = re.findall(r":(\w+)", g.group("groups"))
            group_stack.append(bool(groups) and all(_is_dev_name(x) for x in groups))
            continue
        if re.match(r"^\s*(\w+\s+)?.*\bdo\b\s*(\|.*\|)?\s*$", line) and not _GEM_RE.match(line):
            group_stack.append(bool(group_stack and group_stack[-1]))
            continue
        if line.strip() == "end" and group_stack:
            group_stack.pop()
            continue
        if m := _GEM_RE.match(line):
            rest = m.group("rest")
            versions = _GEM_VERSION_RE.findall(rest)
            inline_groups = re.findall(r"group[s]?:\s*\[?([^\]]+)", rest)
            is_dev = bool(group_stack and group_stack[-1])
            if inline_groups:
                names = re.findall(r":(\w+)", inline_groups[0])
                is_dev = bool(names) and all(_is_dev_name(x) for x in names)
            source = (
                "git"
                if re.search(r"\b(git|github):", rest)
                else ("path" if re.search(r"\bpath:", rest) else "registry")
            )
            deps.append(
                ParsedDependency(
                    m.group("name"),
                    ", ".join(v.strip() for v in versions) or None,
                    "development" if is_dev else "production",
                    source,
                )
            )
    return deps


# --- registry --------------------------------------------------------------------

ParserFn = Callable[[str, str], list[ParsedDependency]]


def parser_for(path: str) -> tuple[str, ParserFn] | None:
    """Return (ecosystem, parser) for a manifest path, or None if unsupported."""
    name = PurePosixPath(path).name
    table: dict[str, tuple[str, ParserFn]] = {
        "package.json": ("npm", lambda t, p: parse_package_json(t)),
        "pyproject.toml": ("PyPI", lambda t, p: parse_pyproject(t)),
        "Pipfile": ("PyPI", lambda t, p: parse_pipfile(t)),
        "setup.cfg": ("PyPI", lambda t, p: parse_setup_cfg(t)),
        "pom.xml": ("Maven", lambda t, p: parse_pom(t)),
        "build.gradle": ("Maven", lambda t, p: parse_gradle(t)),
        "build.gradle.kts": ("Maven", lambda t, p: parse_gradle(t)),
        "Cargo.toml": ("crates.io", lambda t, p: parse_cargo(t)),
        "go.mod": ("Go", lambda t, p: parse_go_mod(t)),
        "composer.json": ("Packagist", lambda t, p: parse_composer(t)),
        "Gemfile": ("RubyGems", lambda t, p: parse_gemfile(t)),
    }
    if name in table:
        return table[name]
    lower = name.lower()
    parent = PurePosixPath(path).parent.name.lower()
    if (lower.startswith("requirements") and lower.endswith((".txt", ".in"))) or (
        parent == "requirements" and lower.endswith(".txt")
    ):
        return "PyPI", parse_requirements
    return None
