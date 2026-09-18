"""Security indicator tests.

Fake credentials are assembled from fragments so that no realistic secret literal exists in
this repository (and secret scanners do not flag the test suite).
"""

import pytest

from app.analyzers.security_analyzer import (
    analyze_security,
    redact,
    scan_file,
    shannon_entropy,
    unpinned_base_images,
)
from app.services.repository_tree import RepositoryTree, TreeEntry

GH_TOKEN = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
AWS_KEY = "AK" + "IA" + "IOSFODNN7EXAMPLE"  # AWS's documented example key id
STRIPE = "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc"
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"


def rules(findings) -> set[str]:
    return {f.rule for f in findings}


def test_detects_known_token_formats_and_redacts_them() -> None:
    text = f'token = "{GH_TOKEN}"\naws = "{AWS_KEY}"\nstripe = "{STRIPE}"\n{PRIVATE_KEY}\n'
    findings = scan_file("src/config.py", text)
    assert {
        "secret.github-token",
        "secret.aws-access-key",
        "secret.stripe-live-key",
        "secret.private-key",
    } <= rules(findings)
    for f in findings:
        assert GH_TOKEN not in (f.evidence or "")
        assert STRIPE not in (f.evidence or "")
    gh = next(f for f in findings if f.rule == "secret.github-token")
    assert gh.severity == "high" and gh.line == 1 and "********" in (gh.evidence or "")


def test_generic_assignment_filters_placeholders_and_low_entropy() -> None:
    real = "api_key = 'Zx9#Lq2@Vr7!Tm4$'"
    placeholders = "\n".join(
        [
            "password = 'changeme123'",
            "api_key = 'your_api_key_here'",
            "secret = '${SECRET_FROM_ENV}'",
            "password = 'aaaaaaaaaaaa'",  # low entropy
            "token = os.environ['TOKEN']",
        ]
    )
    assert rules(scan_file("app.py", real)) == {"secret.generic-assignment"}
    assert "secret.generic-assignment" not in rules(scan_file("app.py", placeholders))


def test_findings_in_tests_are_downgraded() -> None:
    finding = scan_file("tests/test_api.py", f'TOKEN = "{GH_TOKEN}"')[0]
    assert finding.in_test and finding.severity == "medium"


def test_connection_strings() -> None:
    remote = scan_file("app/db.py", 'URL = "postgres://admin:S3cr3tPw@db.prod.example.net/app"')
    assert remote[0].rule == "secret.connection-string" and remote[0].severity == "medium"
    local = scan_file("compose.py", 'URL = "postgres://postgres:devpass@localhost:5432/app"')
    assert local[0].severity == "low"
    templated = scan_file("app/db.py", 'URL = "postgres://u:${DB_PASSWORD}@db.example.net/app"')
    assert "secret.connection-string" not in rules(templated)


@pytest.mark.parametrize(
    ("path", "line", "rule"),
    [
        ("a.py", "result = eval(user_input)", "code.python-eval"),
        ("a.py", "subprocess.run(cmd, shell=True)", "code.python-shell-true"),
        ("a.py", "data = pickle.loads(blob)", "code.python-pickle"),
        ("a.py", "cfg = yaml.load(f)", "code.python-yaml-load"),
        ("a.py", "requests.get(url, verify=False)", "code.tls-verify-disabled"),
        ("a.go", "tls.Config{InsecureSkipVerify: true}", "code.tls-verify-disabled"),
        ("a.ts", "el.innerHTML = html", "code.js-inner-html"),
        ("a.jsx", "<div dangerouslySetInnerHTML={{__html: x}} />", "code.js-inner-html"),
        ("a.js", "const f = new Function(body)", "code.js-eval"),
        ("a.php", "unserialize($_GET['x']);", "code.php-dangerous"),
        ("app/settings.py", "DEBUG = True", "config.debug-enabled"),
        ("install.sh", "curl -fsSL https://get.example.sh | sudo bash", "docker.curl-pipe-shell"),
        (
            "main.py",
            "app.add_middleware(CORSMiddleware, allow_origins=['*'])",
            "code.cors-wildcard",
        ),
    ],
)
def test_dangerous_code_patterns(path: str, line: str, rule: str) -> None:
    assert rule in rules(scan_file(path, line))


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("a.py", "cfg = yaml.load(f, Loader=yaml.SafeLoader)"),
        ("a.py", "model.eval()"),
        ("a.ts", "if (el.innerHTML === expected) {}"),
        ("a.js", "retrieval(x)"),
        ("docs/guide.md", "Never call eval(user_input)"),  # documentation is not code
    ],
)
def test_dangerous_code_false_positives_avoided(path: str, line: str) -> None:
    found = rules(scan_file(path, line))
    assert not {r for r in found if r.startswith("code.")}


def test_insecure_http_excludes_local_and_namespaces() -> None:
    text = "\n".join(
        [
            'API = "http://api.example-service.com/v1"',
            'LOCAL = "http://localhost:8000"',
            'NS = "http://www.w3.org/2000/svg"',
            'LAN = "http://192.168.1.10/status"',
        ]
    )
    findings = [f for f in scan_file("src/client.py", text) if f.rule == "transport.insecure-http"]
    assert [f.line for f in findings] == [1]
    assert scan_file("README.md", "see http://insecure.example-service.com") == []


def test_github_actions_rules() -> None:
    workflow = """
on:
  pull_request_target:
permissions: write-all
jobs:
  x:
    steps:
      - uses: actions/checkout@v4
      - uses: some-org/deploy-action@v2
      - uses: pinned/action@0123456789abcdef0123456789abcdef01234567
      - run: echo "${{ github.event.issue.title }}"
"""
    found = scan_file(".github/workflows/ci.yml", workflow)
    by_rule = {f.rule: f for f in found}
    assert {
        "ci.pull-request-target",
        "ci.write-all-permissions",
        "ci.script-injection",
        "ci.unpinned-action",
    } <= set(by_rule)
    unpinned = [f for f in found if f.rule == "ci.unpinned-action"]
    assert len(unpinned) == 1 and "deploy-action" in (unpinned[0].evidence or "")


def test_dockerfile_base_images() -> None:
    dockerfile = """ARG BASE=python:3.12
FROM node AS builder
FROM ${BASE}
FROM builder AS final
FROM python:3.12-slim
FROM ubuntu:latest
FROM alpine@sha256:abcdef
FROM scratch
FROM registry.example.com:5000/team/app
"""
    assert unpinned_base_images(dockerfile) == [
        (2, "node"),
        (6, "ubuntu:latest"),
        (9, "registry.example.com:5000/team/app"),
    ]


def test_analyze_security_end_to_end() -> None:
    files = {
        ".env": "SECRET=1",
        ".env.example": "SECRET=",
        "deploy/id_rsa": "x",
        "infra/terraform.tfstate": "{}",
        "tests/fixtures/cert.pem": "x",
        "web/app.ts": "const k = process.env.NEXT_PUBLIC_STRIPE_SECRET_KEY;\n"
        "const p = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;\n",
        "api/main.py": "import os\nDB = os.getenv('DATABASE_URL')\n",
        ".gitignore": "node_modules/\n__pycache__/\n",
        "SECURITY.md": "Report privately.",
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", len(t)) for p, t in files.items()])
    result = analyze_security(tree, files, has_lockfiles=False)

    sensitive = {f.path: f for f in result.findings if f.rule == "file.sensitive"}
    assert set(sensitive) == {
        ".env",
        "deploy/id_rsa",
        "infra/terraform.tfstate",
        "tests/fixtures/cert.pem",
    }
    assert sensitive[".env"].severity == "high"
    assert sensitive["tests/fixtures/cert.pem"].in_test
    exposed = [f for f in result.findings if f.rule == "env.client-exposed-secret"]
    assert [f.evidence for f in exposed] == ["NEXT_PUBLIC_STRIPE_SECRET_KEY"]
    assert "DATABASE_URL" in result.env_variables and result.env_variable_files == 2
    assert "gitignore.env-not-excluded" in rules(result.findings)
    hygiene = {h.key: h.passed for h in result.hygiene}
    assert hygiene == {
        "gitignore": True,
        "gitignore_env": False,
        "security_policy": True,
        "dependency_updates": False,
        "lockfiles": False,
        "codeowners": False,
    }
    assert result.findings[0].severity == "high"
    assert "not confirmed vulnerabilities" in result.disclaimer
    assert "secure" not in result.coverage_note
    assert result.counts_by_severity["high"] >= 3
    assert any(r.id == "docker.unpinned-base-image" for r in result.rules)


def test_helpers() -> None:
    assert shannon_entropy("aaaa") == 0
    assert shannon_entropy("abcd") == 2
    assert redact("abcdefghijkl") == "abcd********(12 chars)"
    assert redact("short") == "********(5 chars)"


def test_sensitive_files_in_fixtures_are_aggregated() -> None:
    paths = [f"test/e2e/app{i}/.env" for i in range(10)] + ["bench/app/.env.dev", ".env.prod"]
    tree = RepositoryTree("sha", [TreeEntry(p, "file", 5) for p in paths])
    result = analyze_security(tree, {}, has_lockfiles=True)
    sensitive = [f for f in result.findings if f.rule == "file.sensitive"]
    assert [f.path for f in sensitive if not f.in_test] == [".env.prod"]
    summary = [f for f in sensitive if "more in test/example paths" in f.title]
    assert len(summary) == 1 and summary[0].severity == "info"
    assert "+8 more" in summary[0].title  # 11 in test paths: 3 listed, 8 summarized
    assert len(sensitive) == 5


def test_code_rules_ignore_strings_and_comments_and_local_hosts() -> None:
    text = "\n".join(
        [
            'DESCRIPTION = "eval()/exec() on untrusted input is dangerous"',
            "# never call pickle.loads(data) on user input",
            "result = eval(expression)  # flagged: a real call",
        ]
    )
    findings = [f for f in scan_file("rules.py", text) if f.rule.startswith("code.")]
    assert [(f.rule, f.line) for f in findings] == [("code.python-eval", 3)]
    compose = scan_file("app/config.py", 'API = "http://api:8000/v1"')
    assert not [f for f in compose if f.rule == "transport.insecure-http"]


def test_env_inventory_ignores_test_and_example_files() -> None:
    files = {
        "src/app.ts": "const u = process.env.DATABASE_URL;",
        "tests/app.test.ts": "process.env.NEXT_PUBLIC_STRIPE_SECRET_KEY = 'x';",
        "examples/demo.py": "import os\nos.getenv('SPAM')",
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", len(t)) for p, t in files.items()])
    result = analyze_security(tree, files, has_lockfiles=True)
    assert result.env_variables == ["DATABASE_URL"]
    assert not [f for f in result.findings if f.rule == "env.client-exposed-secret"]
