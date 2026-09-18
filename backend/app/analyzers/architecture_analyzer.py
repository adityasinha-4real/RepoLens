"""Architecture: frameworks, project type, entry points, modules and their import relationships.

Relationships between modules come only from resolved import statements (see import_graph).
Module roles are inferred from directory names and are labelled as such.
"""

import json
import posixpath
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from app.analyzers.file_classifier import (
    FileCategory,
    classify,
    ignored_segment,
    is_auxiliary_path,
)
from app.analyzers.import_graph import build_import_graph
from app.schemas.architecture import (
    ArchitectureAnalysis,
    ComposeService,
    Detection,
    EntryPoint,
    FileHub,
    ImportResolution,
    InfraItem,
    Module,
    ModuleEdge,
)
from app.schemas.dependencies import Dependency
from app.services.content_fetcher import is_manifest
from app.services.repository_tree import RepositoryTree

MAX_MODULES = 40
EXPANDABLE_DIRS = (
    "src",
    "lib",
    "app",
    "pkg",
    "internal",
    "source",
    "packages",
    "apps",
    "services",
    "libs",
    "crates",
    "modules",
    "cmd",
    "components",
)

METHODOLOGY = (
    "Frameworks are detected from declared dependencies and well-known configuration files. "
    "Each detection lists its evidence. Modules are workspace packages or the repository's "
    "major directories. Module roles are inferred from directory names. Edges between modules "
    "are drawn only for import statements that resolve unambiguously to files in this "
    "repository (Python, JavaScript/TypeScript, Go, Rust, Java/Kotlin), using the downloaded "
    "files. Ambiguous imports are counted as unresolved, never guessed."
)

# fmt: off
# dependency name (exact, or prefix when ending with '*') -> (framework, category)
FRAMEWORKS: dict[str, dict[str, tuple[str, str]]] = {
    "npm": {
        "next": ("Next.js", "frontend"), "react": ("React", "frontend"),
        "vue": ("Vue", "frontend"), "nuxt": ("Nuxt", "frontend"), "svelte": ("Svelte", "frontend"),
        "@sveltejs/kit": ("SvelteKit", "frontend"), "@angular/core": ("Angular", "frontend"),
        "solid-js": ("Solid", "frontend"), "astro": ("Astro", "frontend"),
        "@remix-run/react": ("Remix", "frontend"), "preact": ("Preact", "frontend"),
        "express": ("Express", "backend"), "fastify": ("Fastify", "backend"),
        "koa": ("Koa", "backend"), "@nestjs/core": ("NestJS", "backend"),
        "hono": ("Hono", "backend"), "@hapi/hapi": ("hapi", "backend"),
        "electron": ("Electron", "desktop"), "@tauri-apps/api": ("Tauri", "desktop"),
        "react-native": ("React Native", "mobile"), "expo": ("Expo", "mobile"),
        "@prisma/client": ("Prisma", "orm"), "prisma": ("Prisma", "orm"),
        "mongoose": ("Mongoose", "orm"), "typeorm": ("TypeORM", "orm"),
        "drizzle-orm": ("Drizzle", "orm"), "sequelize": ("Sequelize", "orm"),
        "graphql": ("GraphQL", "api"), "@trpc/server": ("tRPC", "api"),
        "socket.io": ("Socket.IO", "realtime"), "vite": ("Vite", "build"),
        "webpack": ("webpack", "build"), "tailwindcss": ("Tailwind CSS", "styling"),
        "commander": ("Commander", "cli"), "yargs": ("yargs", "cli"),
        "@tensorflow/tfjs": ("TensorFlow.js", "ml"),
    },
    "PyPI": {
        "django": ("Django", "backend"), "flask": ("Flask", "backend"),
        "fastapi": ("FastAPI", "backend"), "starlette": ("Starlette", "backend"),
        "tornado": ("Tornado", "backend"), "aiohttp": ("aiohttp", "backend"),
        "sanic": ("Sanic", "backend"), "litestar": ("Litestar", "backend"),
        "streamlit": ("Streamlit", "frontend"), "gradio": ("Gradio", "frontend"),
        "celery": ("Celery", "messaging"), "sqlalchemy": ("SQLAlchemy", "orm"),
        "django-rest-framework": ("Django REST framework", "api"),
        "djangorestframework": ("Django REST framework", "api"),
        "torch": ("PyTorch", "ml"), "tensorflow": ("TensorFlow", "ml"), "jax": ("JAX", "ml"),
        "scikit-learn": ("scikit-learn", "ml"), "transformers": ("Transformers", "ml"),
        "pandas": ("pandas", "data"), "polars": ("Polars", "data"), "pyspark": ("PySpark", "data"),
        "apache-airflow": ("Airflow", "data"), "dbt-core": ("dbt", "data"),
        "click": ("Click", "cli"), "typer": ("Typer", "cli"), "scrapy": ("Scrapy", "crawler"),
        "langchain": ("LangChain", "ml"),
    },
    "Maven": {
        "org.springframework.boot:*": ("Spring Boot", "backend"),
        "org.springframework:*": ("Spring", "backend"), "io.quarkus:*": ("Quarkus", "backend"),
        "io.micronaut:*": ("Micronaut", "backend"), "io.ktor:*": ("Ktor", "backend"),
        "androidx.*": ("Android", "mobile"), "org.hibernate*": ("Hibernate", "orm"),
        "info.picocli:picocli": ("picocli", "cli"),
    },
    "crates.io": {
        "actix-web": ("Actix Web", "backend"), "axum": ("Axum", "backend"),
        "rocket": ("Rocket", "backend"), "warp": ("warp", "backend"),
        "tokio": ("Tokio", "runtime"), "clap": ("clap", "cli"), "tauri": ("Tauri", "desktop"),
        "bevy": ("Bevy", "game"), "diesel": ("Diesel", "orm"), "sqlx": ("SQLx", "orm"),
    },
    "Go": {
        "github.com/gin-gonic/gin": ("Gin", "backend"), "github.com/labstack/echo*":
        ("Echo", "backend"), "github.com/gofiber/fiber*": ("Fiber", "backend"),
        "github.com/go-chi/chi*": ("chi", "backend"), "github.com/gorilla/mux": ("gorilla/mux",
        "backend"), "github.com/spf13/cobra": ("Cobra", "cli"),
        "google.golang.org/grpc": ("gRPC", "api"), "gorm.io/gorm": ("GORM", "orm"),
    },
    "Packagist": {
        "laravel/framework": ("Laravel", "backend"), "symfony/*": ("Symfony", "backend"),
        "slim/slim": ("Slim", "backend"),
    },
    "RubyGems": {
        "rails": ("Ruby on Rails", "backend"), "sinatra": ("Sinatra", "backend"),
        "hanami": ("Hanami", "backend"), "thor": ("Thor", "cli"),
    },
}

FILE_SIGNALS: list[tuple[str, str, str]] = [
    ("manage.py", "Django", "backend"), ("angular.json", "Angular", "frontend"),
    ("pubspec.yaml", "Flutter/Dart", "mobile"), ("AndroidManifest.xml", "Android", "mobile"),
    ("Podfile", "CocoaPods (iOS)", "mobile"), ("Package.swift", "Swift Package", "build"),
    ("CMakeLists.txt", "CMake", "build"), ("hardhat.config.js", "Hardhat", "blockchain"),
    ("foundry.toml", "Foundry", "blockchain"), ("Chart.yaml", "Helm", "infra"),
]

ROLE_BY_NAME: list[tuple[tuple[str, ...], str]] = [
    (("api", "apis", "routes", "routers", "router", "controllers", "controller", "handlers",
      "endpoints", "rest", "graphql", "resolvers", "views_api", "rpc"), "API / routing"),
    (("components", "ui", "views", "pages", "screens", "layouts", "widgets", "templates",
      "public", "static", "styles", "assets", "frontend", "client", "web", "webapp", "www"),
     "UI / presentation"),
    (("services", "service", "domain", "core", "business", "usecases", "use_cases", "logic",
      "features", "engine", "server", "backend"), "Core / services"),
    (("models", "model", "entities", "entity", "schemas", "schema", "types", "dto", "db",
      "database", "migrations", "repositories", "repository", "dal", "persistence", "prisma",
      "data", "store", "stores"), "Data / persistence"),
    (("middleware", "middlewares", "auth", "security", "guards", "permissions"),
     "Middleware / auth"),
    (("hooks", "state", "redux", "context", "contexts", "signals"), "State management"),
    (("utils", "util", "lib", "libs", "helpers", "helper", "common", "shared", "pkg",
      "internal", "support", "tools"), "Shared / library code"),
    (("config", "configs", "configuration", "settings", "conf", "env"), "Configuration"),
    (("tests", "test", "__tests__", "spec", "specs", "e2e", "integration", "testing",
      "fixtures", "benchmarks", "bench"), "Tests"),
    (("docs", "doc", "documentation", "examples", "example", "samples", "demo", "website"),
     "Documentation / examples"),
    (("scripts", "script", "bin", "cmd", "cli", "tasks"), "Scripts / entry points"),
    ((".github", ".circleci", "ci", "deploy", "deployment", "infra", "infrastructure",
      "terraform", "k8s", "kubernetes", "helm", "docker", "ops", ".devcontainer"),
     "Infrastructure / CI"),
]
# fmt: on


def _role_for(name: str) -> str | None:
    lowered = name.lower()
    for names, role in ROLE_BY_NAME:
        if lowered in names:
            return role
    return None


def _match_framework(ecosystem: str, name: str) -> tuple[str, str] | None:
    table = FRAMEWORKS.get(ecosystem, {})
    if name in table:
        return table[name]
    lowered = name.lower()
    if lowered in table:
        return table[lowered]
    for key, value in table.items():
        if key.endswith("*") and name.startswith(key[:-1]):
            return value
    return None


def detect_frameworks(paths: list[str], dependencies: list[Dependency]) -> list[Detection]:
    found: dict[str, Detection] = {}
    for dep in dependencies:
        if dep.scope not in ("production", "peer", "development", "build"):
            continue
        match = _match_framework(dep.ecosystem, dep.name)
        if not match:
            continue
        name, category = match
        # Dev-only matches count for build tooling and styling, not as the app's framework.
        if dep.scope == "development" and category not in ("build", "styling", "cli"):
            continue
        found.setdefault(
            name, Detection(name=name, category=category, evidence=f"{dep.manifest}: '{dep.name}'")
        )
    names = {PurePosixPath(p).name for p in paths}
    for filename, name, category in FILE_SIGNALS:
        if filename in names and name not in found:
            path = next(p for p in paths if PurePosixPath(p).name == filename)
            found[name] = Detection(name=name, category=category, evidence=path)
    for p in paths:
        if PurePosixPath(p).name.startswith("next.config.") and "Next.js" not in found:
            found["Next.js"] = Detection(name="Next.js", category="frontend", evidence=p)
    order = ["frontend", "backend", "mobile", "desktop", "api", "cli", "ml", "data", "orm"]
    return sorted(
        found.values(),
        key=lambda d: (order.index(d.category) if d.category in order else 99, d.name),
    )


def detect_monorepo(paths: list[str], contents: dict[str, str]) -> tuple[str | None, list[str]]:
    names = {p for p in paths if "/" not in p}
    tool = None
    for filename, name in (
        ("pnpm-workspace.yaml", "pnpm workspaces"),
        ("lerna.json", "Lerna"),
        ("nx.json", "Nx"),
        ("turbo.json", "Turborepo"),
        ("go.work", "Go workspaces"),
        ("rush.json", "Rush"),
    ):
        if filename in names:
            tool = name
            break
    root_pkg = contents.get("package.json")
    if tool is None and root_pkg and '"workspaces"' in root_pkg:
        tool = "npm/yarn workspaces"
    cargo = contents.get("Cargo.toml")
    if tool is None and cargo and "[workspace]" in cargo:
        tool = "Cargo workspace"
    manifest_dirs = sorted(
        {
            posixpath.dirname(p)
            for p in paths
            if "/" in p and is_manifest(p) and not PurePosixPath(p).name.startswith("requirements")
        }
    )
    globs = workspace_globs(contents)
    if globs:
        include = [_glob_regex(g) for g in globs if not g.startswith("!")]
        exclude = [_glob_regex(g[1:]) for g in globs if g.startswith("!")]
        packages = [
            d
            for d in manifest_dirs
            if any(r.fullmatch(d) for r in include) and not any(r.fullmatch(d) for r in exclude)
        ]
    else:
        packages = [d for d in manifest_dirs if not is_auxiliary_path(d + "/")]
    if tool is None and len(packages) < 2:
        return None, []
    if tool is None:
        tool = "multiple manifests"
    return tool, packages[:60]


def _glob_regex(glob: str) -> re.Pattern[str]:
    glob = glob.strip().strip("/").removeprefix("./")
    out = ""
    i = 0
    while i < len(glob):
        if glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out.replace("/.*", "(?:/.*)?"))


def workspace_globs(contents: dict[str, str]) -> list[str]:
    """Workspace member patterns declared by pnpm, npm/yarn, Lerna, Cargo or go.work."""
    globs: list[str] = []
    pnpm = contents.get("pnpm-workspace.yaml")
    if pnpm:
        in_packages = False
        for line in pnpm.splitlines():
            if re.match(r"^packages\s*:", line):
                in_packages = True
                continue
            if in_packages:
                m = re.match(r"^\s+-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
                if m:
                    globs.append(m.group(1))
                elif line.strip() and not line.startswith((" ", "\t")):
                    in_packages = False
    for name in ("package.json", "lerna.json"):
        try:
            data = json.loads(contents.get(name, "") or "null")
        except (ValueError, RecursionError):
            data = None
        if isinstance(data, dict):
            ws = data.get("workspaces") if name == "package.json" else data.get("packages")
            if isinstance(ws, dict):
                ws = ws.get("packages")
            if isinstance(ws, list):
                globs += [g for g in ws if isinstance(g, str)]
    cargo = contents.get("Cargo.toml")
    if cargo and "[workspace]" in cargo:
        try:
            members = tomllib.loads(cargo).get("workspace", {}).get("members", [])
        except (tomllib.TOMLDecodeError, RecursionError):
            members = []
        globs += [m for m in members if isinstance(m, str)]
    go_work = contents.get("go.work")
    if go_work:
        globs += [
            m.removeprefix("./")
            for m in re.findall(r"^\s*(?:use\s+)?(\./[\w./-]+)", go_work, re.MULTILINE)
        ]
    return globs[:100]


def _choose_module_paths(paths: list[str], packages: list[str]) -> list[str]:
    if len(packages) >= 2:
        # Packages plus every top-level directory: longest-prefix matching routes package
        # files to their package and everything else to its top-level directory.
        chosen = set(packages) | {p.split("/", 1)[0] for p in paths if "/" in p}
        return sorted(chosen)

    # Source files below every directory, and the directory tree itself.
    source_below: Counter[str] = Counter()
    children: dict[str, set[str]] = defaultdict(set)
    direct_files: Counter[str] = Counter()
    for p in paths:
        parts = p.split("/")
        # Only production source decides where the code "lives"; large test suites would
        # otherwise dilute the share of the real source directory.
        is_source = classify(p).category == FileCategory.SOURCE
        direct_files["/".join(parts[:-1])] += 1
        for i in range(1, len(parts)):
            parent, child = "/".join(parts[: i - 1]), "/".join(parts[:i])
            children[parent].add(child)
            if is_source:
                source_below[child] += 1
    total_source = sum(source_below[c] for c in children[""]) or 1

    def expand(directory: str, depth: int) -> list[str]:
        subdirs = sorted(children.get(directory, ()))
        with_source = [d for d in subdirs if source_below[d] > 0]
        if (
            depth < 3
            and len(with_source) == 1
            and direct_files[directory] == 0
            and len(subdirs) == 1
        ):
            return expand(with_source[0], depth + 1)  # e.g. src/<package>/...
        if depth < 3 and len(with_source) >= 2:
            return subdirs + ([directory] if direct_files[directory] else [])
        return [directory]

    modules: list[str] = []
    for top in sorted(children[""]):
        share = source_below[top] / total_source
        # Split the directory that holds most of the code into its sub-modules; conventional
        # container names (src, packages, ...) are split at a lower share.
        threshold = 0.3 if top.lower() in EXPANDABLE_DIRS else 0.5
        modules += expand(top, 0) if share >= threshold else [top]
    return modules


def _module_for(path: str, module_paths: list[str]) -> str:
    best = ""
    for m in module_paths:
        if (path == m or path.startswith(m + "/")) and len(m) > len(best):
            best = m
    return best


def detect_entry_points(paths: list[str], contents: dict[str, str]) -> list[EntryPoint]:
    points: list[EntryPoint] = []
    seen: set[str] = set()

    def add(path: str, kind: str, evidence: str) -> None:
        if path not in seen and len(points) < 25:
            seen.add(path)
            points.append(EntryPoint(path=path, kind=kind, evidence=evidence))

    path_set = set(paths)
    conventions = [
        ("manage.py", "Django management"),
        ("wsgi.py", "WSGI application"),
        ("asgi.py", "ASGI application"),
        ("main.go", "Go main package"),
        ("src/main.rs", "Rust binary"),
        ("src/lib.rs", "Rust library"),
        ("Program.cs", "C# program"),
        ("app/page.tsx", "Next.js app route"),
        ("app/layout.tsx", "Next.js root layout"),
        ("pages/index.tsx", "Next.js page"),
        ("pages/index.js", "Next.js page"),
        ("src/main.ts", "Application bootstrap"),
        ("src/main.tsx", "Application bootstrap"),
        ("src/index.ts", "Package entry"),
        ("src/index.js", "Package entry"),
        ("index.js", "Package entry"),
        ("server.js", "Node server"),
        ("app.py", "Python application"),
        ("main.py", "Python application"),
    ]
    for p in sorted(path_set):
        if is_auxiliary_path(p):
            continue  # examples, fixtures, tests and benchmarks are not the product
        name = PurePosixPath(p).name
        for suffix, kind in conventions:
            if (
                (p == suffix or p.endswith("/" + suffix))
                and ignored_segment(p) is None
                and p.count("/") <= suffix.count("/") + 2
            ):
                add(p, kind, "file naming convention")
        if name == "__main__.py":
            add(p, "Python module entry", "__main__.py")
        if name == "main.go" and "/cmd/" in f"/{p}":
            add(p, "Go command", "cmd/<name>/main.go convention")

    for p, text in contents.items():
        if is_auxiliary_path(p):
            continue
        name = PurePosixPath(p).name
        if name == "package.json":
            try:
                data = json.loads(text)
            except (ValueError, RecursionError):
                continue
            if not isinstance(data, dict):
                continue
            base = posixpath.dirname(p)
            for field in ("main", "module"):
                if isinstance(data.get(field), str):
                    add(
                        posixpath.normpath(posixpath.join(base, data[field])),
                        "Package entry",
                        f'{p} "{field}"',
                    )
            bins = data.get("bin")
            if isinstance(bins, str):
                bins = {data.get("name", "bin"): bins}
            if isinstance(bins, dict):
                for cmd, target in list(bins.items())[:5]:
                    if isinstance(target, str):
                        add(
                            posixpath.normpath(posixpath.join(base, target)),
                            "CLI command",
                            f"{p} bin '{cmd}'",
                        )
        elif name == "pyproject.toml":
            try:
                data = tomllib.loads(text)
            except (tomllib.TOMLDecodeError, RecursionError):
                continue
            scripts = dict(data.get("project", {}).get("scripts", {}) or {})
            scripts |= data.get("tool", {}).get("poetry", {}).get("scripts", {}) or {}
            for cmd, target in list(scripts.items())[:5]:
                if isinstance(target, str):
                    add(f"{target}", "CLI command", f"{p} script '{cmd}'")
        elif name.startswith("Dockerfile"):
            for line in text.splitlines():
                m = re.match(r"^\s*(ENTRYPOINT|CMD)\s+(.+)$", line)
                if m:
                    add(f"{p}:{m.group(1)}", "Container command", m.group(2).strip()[:120])
        elif p.endswith(".py") and re.search(
            r"^if __name__ == ['\"]__main__['\"]:", text, re.MULTILINE
        ):
            add(p, "Python script", 'if __name__ == "__main__"')
        elif p.endswith((".java", ".kt")) and "@SpringBootApplication" in text:
            add(p, "Spring Boot application", "@SpringBootApplication")
    return points


def parse_compose_services(text: str) -> list[ComposeService]:
    """Minimal, indentation-based reader for the `services:` map of a Compose file."""
    services: list[ComposeService] = []
    lines = text.splitlines()
    in_services = False
    service_indent: int | None = None
    current: ComposeService | None = None
    in_depends = False
    depends_indent = 0
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            in_services = line.startswith("services:")
            current = None
            continue
        if not in_services:
            continue
        if service_indent is None:
            service_indent = indent
        if indent == service_indent and line.endswith(":"):
            current = ComposeService(name=line[:-1].strip("'\""))
            services.append(current)
            in_depends = False
            continue
        if current is None:
            continue
        if in_depends and indent > depends_indent:
            item = (
                line[2:].strip()
                if line.startswith("- ")
                else (line[:-1] if line.endswith(":") else None)
            )
            if item:
                current.depends_on.append(item.strip("'\""))
            continue
        in_depends = False
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "image":
            current.image = value.strip().strip("'\"") or None
        elif key == "build":
            current.build = True
        elif key == "depends_on":
            value = value.strip()
            if value.startswith("["):
                current.depends_on += [
                    v.strip(" '\"") for v in value.strip("[]").split(",") if v.strip()
                ]
            else:
                in_depends, depends_indent = True, indent
    return services[:30]


def detect_infrastructure(
    paths: list[str], contents: dict[str, str]
) -> tuple[list[InfraItem], list[ComposeService]]:
    items: list[InfraItem] = []
    compose: list[ComposeService] = []
    tf_files = [p for p in paths if p.endswith(".tf")]
    for p in paths:
        name = PurePosixPath(p).name
        if name.startswith("Dockerfile") or name == "Containerfile" or name.endswith(".dockerfile"):
            items.append(InfraItem(kind="Container image", path=p, detail="Dockerfile"))
        elif name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            services = parse_compose_services(contents.get(p, ""))
            compose += services
            items.append(
                InfraItem(
                    kind="Docker Compose",
                    path=p,
                    detail=f"{len(services)} service(s)" if p in contents else "not downloaded",
                )
            )
        elif name == "Chart.yaml":
            items.append(InfraItem(kind="Helm chart", path=p, detail="Kubernetes package"))
        elif name in ("serverless.yml", "serverless.yaml"):
            items.append(InfraItem(kind="Serverless Framework", path=p, detail="serverless.yml"))
        elif name in (
            "vercel.json",
            "netlify.toml",
            "fly.toml",
            "render.yaml",
            "app.yaml",
            "Procfile",
            "railway.json",
            "wrangler.toml",
        ):
            items.append(InfraItem(kind="Deployment config", path=p, detail=name))
        elif (
            p.endswith((".yml", ".yaml"))
            and p in contents
            and re.search(
                r"^kind:\s*(Deployment|StatefulSet|DaemonSet|Service|Ingress|CronJob)\b",
                contents[p],
                re.MULTILINE,
            )
        ):
            items.append(
                InfraItem(
                    kind="Kubernetes manifest",
                    path=p,
                    detail="kind: "
                    + re.search(r"^kind:\s*(\w+)", contents[p], re.MULTILINE).group(1),
                )
            )  # type: ignore[union-attr]
    if tf_files:
        providers = sorted(
            {
                m
                for p in tf_files
                if p in contents
                for m in re.findall(r'provider\s+"([\w-]+)"', contents[p])
            }
        )
        items.append(
            InfraItem(
                kind="Terraform",
                path=posixpath.dirname(tf_files[0]) or ".",
                detail=f"{len(tf_files)} .tf file(s)"
                + (f"; providers: {', '.join(providers)}" if providers else ""),
            )
        )
    return items[:40], compose


def _project_types(
    frameworks: list[Detection],
    monorepo_tool: str | None,
    paths: list[str],
    entry_points: list[EntryPoint],
) -> list[Detection]:
    types: list[Detection] = []
    by_category: dict[str, list[Detection]] = defaultdict(list)
    for f in frameworks:
        by_category[f.category].append(f)
    labels = [
        ("frontend", "Web frontend"),
        ("backend", "Web / API service"),
        ("mobile", "Mobile app"),
        ("desktop", "Desktop app"),
        ("cli", "Command-line tool"),
        ("ml", "Machine learning"),
        ("data", "Data processing"),
    ]
    for category, label in labels:
        if by_category.get(category):
            evidence = ", ".join(f.name for f in by_category[category][:3])
            types.append(Detection(name=label, category=category, evidence=evidence))
    if monorepo_tool:
        types.append(Detection(name="Monorepo", category="structure", evidence=monorepo_tool))
    if not any(t.category in ("frontend", "backend", "mobile", "desktop", "cli") for t in types):
        library_signal = next(
            (e for e in entry_points if e.kind in ("Package entry", "Rust library")), None
        )
        if library_signal:
            types.append(
                Detection(
                    name="Library / package", category="library", evidence=library_signal.evidence
                )
            )
    if sum(p.endswith(".tf") for p in paths) >= 3 and not types:
        types.append(
            Detection(name="Infrastructure as code", category="infra", evidence="Terraform files")
        )
    return types


def analyze_architecture(
    tree: RepositoryTree, contents: dict[str, str], dependencies: list[Dependency]
) -> ArchitectureAnalysis:
    paths = [e.path for e in tree.files() if ignored_segment(e.path) is None]
    size_by_path = {e.path: e.size for e in tree.files()}
    frameworks = detect_frameworks(paths, dependencies)
    monorepo_tool, packages = detect_monorepo(paths, contents)
    entry_points = detect_entry_points(paths, contents)
    infrastructure, compose = detect_infrastructure(paths, contents)

    module_paths = _choose_module_paths(paths, packages)
    stats: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "source": 0, "bytes": 0, "sampled": 0, "langs": Counter()}
    )
    for p in paths:
        m = _module_for(p, module_paths)
        s = stats[m]
        s["files"] += 1
        s["bytes"] += size_by_path.get(p, 0)
        cls = classify(p)
        if cls.category in (FileCategory.SOURCE, FileCategory.TEST):
            s["source"] += 1
            if cls.language:
                s["langs"][cls.language] += 1
        if p in contents:
            s["sampled"] += 1

    ranked = sorted(stats, key=lambda m: (-stats[m]["files"], m))
    kept = set(ranked[:MAX_MODULES])
    notes: list[str] = []
    if len(ranked) > MAX_MODULES:
        notes.append(f"Showing the {MAX_MODULES} largest of {len(ranked)} modules.")

    package_set = set(packages)
    modules: list[Module] = []
    for m in sorted(kept):
        s = stats[m]
        name = PurePosixPath(m).name if m else "(root)"
        role = _role_for(name)
        role_source = "directory-name" if role else "unknown"
        if m in package_set:
            role_source = "workspace-package"
            role = role or "Workspace package"
        modules.append(
            Module(
                id=m or ".",
                path=m,
                name=name,
                role=role or ("Repository root" if not m else "Module"),
                role_source=role_source,
                files=s["files"],
                source_files=s["source"],
                bytes=s["bytes"],
                languages=[lang for lang, _ in s["langs"].most_common(3)],
                sampled_files=s["sampled"],
            )
        )

    graph = build_import_graph(paths, contents)
    module_edges: Counter[tuple[str, str]] = Counter()
    fan_in: Counter[str] = Counter()
    for (src, dst), count in graph.edges.items():
        if dst in size_by_path:
            fan_in[dst] += 1
        a, b = _module_for(src, module_paths), _module_for(dst, module_paths)
        if a != b and a in kept and b in kept:
            module_edges[(a or ".", b or ".")] += count

    resolution = graph.stats
    if resolution.files_parsed == 0:
        notes.append(
            "No import statements could be analyzed for the supported languages, so "
            "no module relationships are shown."
        )
    return ArchitectureAnalysis(
        project_types=_project_types(frameworks, monorepo_tool, paths, entry_points),
        frameworks=frameworks,
        monorepo_tool=monorepo_tool,
        workspace_packages=packages,
        entry_points=entry_points,
        modules=modules,
        edges=[
            ModuleEdge(source=a, target=b, imports=n)
            for (a, b), n in sorted(module_edges.items(), key=lambda kv: (-kv[1], kv[0]))
        ][:150],
        hubs=[
            FileHub(path=p, imported_by=n)
            for p, n in sorted(fan_in.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ],
        compose_services=compose,
        infrastructure=infrastructure,
        import_resolution=ImportResolution(
            files_parsed=resolution.files_parsed,
            imports_found=resolution.imports_found,
            internal_resolved=resolution.internal_resolved,
            external=resolution.external,
            unresolved=resolution.unresolved,
            languages=sorted(graph.languages),
        ),
        methodology=METHODOLOGY,
        notes=notes,
    )
