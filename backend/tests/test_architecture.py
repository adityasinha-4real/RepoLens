from app.analyzers.architecture_analyzer import (
    analyze_architecture,
    detect_entry_points,
    detect_frameworks,
    detect_monorepo,
    parse_compose_services,
)
from app.analyzers.import_graph import build_import_graph
from app.schemas.dependencies import Dependency
from app.services.repository_tree import RepositoryTree, TreeEntry


def dep(name: str, ecosystem: str, scope: str = "production", manifest: str = "m") -> Dependency:
    return Dependency(
        name=name,
        version="1",
        ecosystem=ecosystem,
        scope=scope,
        manifest=manifest,
        source="registry",
        constraint="exact",
    )


def test_python_imports_resolve_absolute_relative_and_skip_stdlib() -> None:
    files = {
        "app/__init__.py": "",
        "app/main.py": "import os\nimport json\nfrom app.api import routes\nfrom .core import db\n"
        "import requests\n",
        "app/api/__init__.py": "",
        "app/api/routes.py": "from ..core.db import session\nfrom app.models import User\n",
        "app/core/__init__.py": "",
        "app/core/db.py": "",
        "app/models.py": "",
        "app/json.py": "",  # must not capture the stdlib 'json' import
        "src/utils.py": "",
        "lib/utils.py": "",  # both are importable as `utils`: ambiguous
        "tool.py": "import utils\n",
    }
    graph = build_import_graph(list(files), files)
    edges = set(graph.edges)
    assert ("app/main.py", "app/api/__init__.py") in edges or (
        "app/main.py",
        "app/api/routes.py",
    ) in edges
    assert ("app/main.py", "app/core/db.py") in edges  # `from .core import db` -> submodule
    assert ("app/api/routes.py", "app/core/db.py") in edges
    assert ("app/api/routes.py", "app/models.py") in edges
    assert not any(dst == "app/json.py" for _, dst in edges)
    assert graph.stats.unresolved == 1  # `import utils` is ambiguous between src/ and lib/
    assert graph.stats.external == 3  # os, json, requests


def test_js_imports_relative_alias_and_workspace_packages() -> None:
    files = {
        "tsconfig.json": '{\n // comment\n "compilerOptions": {"baseUrl": ".", '
        '"paths": {"@/*": ["./src/*"]},}\n}',
        "src/app/page.tsx": "import { Button } from '@/components/Button'\n"
        "import api from '../lib/api.js'\nimport React from 'react'\n"
        "import {\n  a,\n  b,\n} from './local'\n",
        "src/app/local.ts": "export const a = 1",
        "src/components/Button.tsx": "export {}",
        "src/lib/api.ts": "const x = require('./missing')",
        "packages/ui/package.json": '{"name": "@acme/ui"}',
        "packages/ui/src/index.ts": "",
        "apps/web/index.ts": "import { ui } from '@acme/ui'\nimport x from '@acme/ui/src/index'",
    }
    graph = build_import_graph(list(files), files)
    edges = set(graph.edges)
    assert ("src/app/page.tsx", "src/components/Button.tsx") in edges
    assert ("src/app/page.tsx", "src/lib/api.ts") in edges  # .js specifier -> .ts file
    assert ("src/app/page.tsx", "src/app/local.ts") in edges  # multi-line import
    assert ("apps/web/index.ts", "packages/ui") in edges
    assert ("apps/web/index.ts", "packages/ui/src/index.ts") in edges
    assert graph.stats.external == 1 and graph.stats.unresolved == 1


def test_go_rust_and_jvm_imports() -> None:
    files = {
        "go.mod": "module github.com/acme/svc\n\ngo 1.22\n",
        "cmd/api/main.go": 'package main\n\nimport (\n\t"fmt"\n\th "github.com/acme/svc/internal/'
        'handlers"\n)\n',
        "internal/handlers/h.go": "package handlers\n",
        "crate/src/main.rs": "use crate::net::client;\nuse std::io;\n",
        "crate/src/net/mod.rs": "",
        "java/src/main/java/com/acme/App.java": "import com.acme.service.UserService;\n"
        "import java.util.List;\n",
        "java/src/main/java/com/acme/service/UserService.java": "",
    }
    graph = build_import_graph(list(files), files)
    edges = set(graph.edges)
    assert ("cmd/api/main.go", "internal/handlers") in edges
    assert ("crate/src/main.rs", "crate/src/net/mod.rs") in edges
    assert (
        "java/src/main/java/com/acme/App.java",
        "java/src/main/java/com/acme/service/UserService.java",
    ) in edges


def test_framework_detection_with_evidence() -> None:
    deps = [
        dep("next", "npm", manifest="web/package.json"),
        dep("fastapi", "PyPI"),
        dep("vitest", "npm", "development"),
        dep("vite", "npm", "development"),
        dep("org.springframework.boot:spring-boot-starter-web", "Maven"),
    ]
    found = {d.name: d for d in detect_frameworks(["manage.py"], deps)}
    assert found["Next.js"].category == "frontend"
    assert found["Next.js"].evidence == "web/package.json: 'next'"
    assert found["FastAPI"].category == "backend"
    assert found["Spring Boot"].category == "backend"
    assert found["Vite"].category == "build"  # dev dependency allowed for build tooling
    assert "Django" in found  # from manage.py


def test_monorepo_detection() -> None:
    paths = [
        "package.json",
        "pnpm-workspace.yaml",
        "apps/web/package.json",
        "packages/ui/package.json",
        "examples/demo/package.json",
    ]
    tool, packages = detect_monorepo(paths, {})
    assert tool == "pnpm workspaces"
    assert packages == ["apps/web", "packages/ui"]
    assert detect_monorepo(["package.json", "src/index.ts"], {}) == (None, [])


def test_entry_points() -> None:
    contents = {
        "package.json": '{"name": "cli", "main": "dist/index.js", "bin": {"cli": "./bin/cli.js"}}',
        "pyproject.toml": '[project]\nname="x"\n[project.scripts]\nx = "x.cli:main"\n',
        "Dockerfile": 'FROM python:3.12\nCMD ["uvicorn", "app.main:app"]\n',
        "tools/run.py": "def main(): pass\nif __name__ == '__main__':\n    main()\n",
    }
    paths = [*contents, "manage.py", "cmd/server/main.go", "src/main.rs"]
    points = {p.path: p for p in detect_entry_points(paths, contents)}
    assert points["manage.py"].kind == "Django management"
    assert points["cmd/server/main.go"].kind in ("Go main package", "Go command")
    assert points["dist/index.js"].kind == "Package entry"
    assert points["bin/cli.js"].kind == "CLI command"
    assert points["x.cli:main"].kind == "CLI command"
    assert points["Dockerfile:CMD"].evidence.startswith('["uvicorn"')
    assert points["tools/run.py"].kind == "Python script"


def test_compose_services() -> None:
    compose = """
version: "3.9"
services:
  web:
    build: .
    depends_on:
      - api
  api:
    image: acme/api:1.2
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
  db:
    image: postgres:16
  cache:
    image: "redis:7"
    depends_on: [db]
volumes:
  data:
"""
    services = {s.name: s for s in parse_compose_services(compose)}
    assert set(services) == {"web", "api", "db", "cache"}
    assert services["web"].build and services["web"].depends_on == ["api"]
    assert services["api"].depends_on == ["db", "cache"]
    assert services["cache"].image == "redis:7" and services["cache"].depends_on == ["db"]


def test_analyze_architecture_modules_and_edges() -> None:
    files = {
        "README.md": "# x",
        "src/api/routes.py": "from src.services.users import get_user\n",
        "src/services/users.py": "from src.models.user import User\n",
        "src/models/user.py": "class User: ...\n",
        "src/main.py": "from src.api import routes\n",
        "tests/test_users.py": "from src.services.users import get_user\n",
        "docker-compose.yml": "services:\n  app:\n    build: .\n",
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", len(t)) for p, t in files.items()])
    arch = analyze_architecture(tree, files, [dep("fastapi", "PyPI", manifest="pyproject.toml")])

    modules = {m.id: m for m in arch.modules}
    assert {"src/api", "src/services", "src/models", "src", "tests", "."} <= set(modules)
    assert modules["src/api"].role == "API / routing"
    assert modules["src/services"].role == "Core / services"
    assert modules["src/models"].role == "Data / persistence"
    assert modules["tests"].role == "Tests"
    assert modules["src/api"].role_source == "directory-name"
    edges = {(e.source, e.target) for e in arch.edges}
    assert edges == {
        ("src/api", "src/services"),
        ("src/services", "src/models"),
        ("tests", "src/services"),
        ("src", "src/api"),
    }
    assert arch.hubs[0].path == "src/services/users.py" and arch.hubs[0].imported_by == 2
    assert [t.name for t in arch.project_types] == ["Web / API service"]
    assert arch.compose_services[0].name == "app"
    assert arch.import_resolution.files_parsed == 5


def test_workspace_globs_drive_package_detection() -> None:
    from app.analyzers.architecture_analyzer import workspace_globs

    contents = {
        "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n  - \"apps/**\"\n"
        "  - '!packages/internal-*'\ncatalog:\n  x: 1\n",
        "package.json": '{"workspaces": {"packages": ["tools/cli"]}}',
    }
    assert workspace_globs(contents) == [
        "packages/*",
        "apps/**",
        "!packages/internal-*",
        "tools/cli",
    ]
    paths = [
        "package.json",
        "pnpm-workspace.yaml",
        "packages/ui/package.json",
        "packages/internal-x/package.json",
        "apps/web/package.json",
        "apps/docs/site/package.json",
        "bench/perf/package.json",
        "tools/cli/package.json",
        "packages/ui/src/nested/package.json",
    ]
    tool, packages = detect_monorepo(paths, contents)
    assert tool == "pnpm workspaces"
    assert packages == ["apps/docs/site", "apps/web", "packages/ui", "tools/cli"]


def test_entry_points_skip_examples_and_fixtures() -> None:
    paths = [
        "examples/basic/main.py",
        "test/fixtures/app/page.tsx",
        "bench/app/index.js",
        "src/main.ts",
    ]
    points = [p.path for p in detect_entry_points(paths, {})]
    assert points == ["src/main.ts"]


def test_python_imports_only_resolve_at_plausible_sys_path_roots() -> None:
    files = {
        "src/flask/__init__.py": "",
        "src/flask/app.py": "from flask import helpers",
        "src/flask/helpers.py": "",
        "tests/test_app.py": "import flask; from conftest import fixture",
        "tests/conftest.py": "",
        "tests/apps/inner/flask.py": "",  # fixture module that shadows the name
        "scripts/run.py": "import helpers",  # not importable from scripts/
    }
    graph = build_import_graph(list(files), files)
    edges = set(graph.edges)
    assert ("tests/test_app.py", "src/flask/__init__.py") in edges
    assert ("tests/test_app.py", "tests/conftest.py") in edges  # importer's own directory
    assert ("src/flask/app.py", "src/flask/helpers.py") in edges
    assert not any(dst == "tests/apps/inner/flask.py" for _, dst in edges)
    assert not any(src == "scripts/run.py" for src, _ in edges)
