"""Conservative static security indicators.

Every finding is a *potential* concern found by pattern matching. None of them is a confirmed
vulnerability, and an empty result does not mean the repository is secure. Secrets are
redacted before they are placed in the report.
"""

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.analyzers.file_classifier import FileCategory, classify, ignored_segment, is_test_path
from app.schemas.security import (
    HygieneCheck,
    SecurityAnalysis,
    SecurityFinding,
    SecurityRule,
    Severity,
)
from app.services.repository_tree import RepositoryTree

DISCLAIMER = (
    "These are potential security concerns detected by static pattern matching on a sample "
    "of files. They are indicators, not confirmed vulnerabilities, and may include false "
    "positives. The absence of findings does not mean the repository is secure."
)
MAX_FINDINGS = 300
MAX_PER_RULE_PER_FILE = 5
MAX_LINE_LENGTH = 2000  # longer lines (minified code) are truncated before matching
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: Severity
    category: str
    description: str
    pattern: re.Pattern[str]
    confidence: str = "medium"
    languages: frozenset[str] | None = None  # None: any text file
    filenames: tuple[str, ...] | None = None  # restrict to these basenames / prefixes
    secret: bool = False  # redact the match in evidence
    # Optional post-filter: return None to discard a match, or the severity to report.
    validator: Callable[[re.Match[str]], Severity | None] | None = None


def _r(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


_PY = frozenset({"Python"})
_JS = frozenset({"JavaScript", "TypeScript", "Vue", "Svelte"})

# fmt: off
SECRET_RULES: list[Rule] = [
    Rule("secret.private-key", "Private key material", "high", "secret",
         "A PEM private key block is committed.",
         _r(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"),
         confidence="high", secret=True),
    Rule("secret.aws-access-key", "Possible AWS access key ID", "high", "secret",
         "Matches the AWS access key ID format.",
         _r(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), confidence="high", secret=True),
    Rule("secret.github-token", "Possible GitHub token", "high", "secret",
         "Matches the GitHub personal access / app token format.",
         _r(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})\b"),
         confidence="high", secret=True),
    Rule("secret.slack-token", "Possible Slack token", "high", "secret",
         "Matches the Slack token format.",
         _r(r"\bxox[abposr]-[A-Za-z0-9-]{10,200}"), confidence="high", secret=True),
    Rule("secret.stripe-live-key", "Possible Stripe live secret key", "high", "secret",
         "Matches the Stripe live secret/restricted key format.",
         _r(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,200}\b"), confidence="high", secret=True),
    Rule("secret.google-api-key", "Possible Google API key", "medium", "secret",
         "Matches the Google API key format. Some Google keys are meant to be public; "
         "verify its restrictions.",
         _r(r"\bAIza[0-9A-Za-z_\-]{35}\b"), confidence="high", secret=True),
    Rule("secret.llm-api-key", "Possible AI provider API key", "high", "secret",
         "Matches an OpenAI or Anthropic API key format.",
         _r(r"\bsk-(?:ant-[A-Za-z0-9_\-]{20,200}|proj-[A-Za-z0-9_\-]{20,200}|"
            r"[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20})"), confidence="high", secret=True),
    Rule("secret.npm-token", "Possible npm access token", "high", "secret",
         "Matches the npm access token format.",
         _r(r"\bnpm_[A-Za-z0-9]{36}\b"), confidence="high", secret=True),
    Rule("secret.sendgrid-key", "Possible SendGrid API key", "high", "secret",
         "Matches the SendGrid API key format.",
         _r(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"), confidence="high", secret=True),
    Rule("secret.connection-string", "Credentials in a connection string", "medium", "secret",
         "A database or broker URL contains an inline username and password.",
         _r(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqps?|mssql)"
            r"://[^:\s/'\"@]{1,64}:(?P<password>[^@\s/'\"]{3,128})@(?P<host>[^:/\s'\"]{1,253})"),
         secret=True, validator=lambda m: _connection_string_severity(m)),
]

GENERIC_SECRET_RE = _r(
    r"""(?i)\b(?P<key>[\w.-]{0,40}(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|"""
    r"""auth[_-]?token|client[_-]?secret|private[_-]?key)[\w.-]{0,20})["']?\s*[:=]\s*"""
    r"""["'](?P<value>[^"'\s]{8,200})["']"""
)
_PLACEHOLDER_RE = _r(
    r"(?i)(change.?me|your[_-]|example|sample|dummy|placeholder|xxx|\*\*\*|<[^>]*>|\$\{|\{\{|"
    r"^test|fake|redacted|todo|none|null|secret$|password$|process\.env|os\.environ|getenv)"
)

CODE_RULES: list[Rule] = [
    Rule("code.python-eval", "Dynamic code execution (eval/exec)", "medium", "dangerous-code",
         "eval()/exec() on untrusted input can lead to code execution.",
         _r(r"(?<![\w.])(?:eval|exec)\s*\("), languages=_PY),
    Rule("code.python-shell-true", "Subprocess with shell=True", "medium", "dangerous-code",
         "shell=True with interpolated input can allow command injection.",
         _r(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), languages=_PY),
    Rule("code.python-os-system", "os.system call", "low", "dangerous-code",
         "os.system runs a shell command; prefer subprocess with an argument list.",
         _r(r"\bos\.system\s*\("), languages=_PY),
    Rule("code.python-pickle", "Unpickling data", "medium", "dangerous-code",
         "Unpickling untrusted data can execute arbitrary code.",
         _r(r"\b(?:pickle|cPickle|dill)\.loads?\s*\("), languages=_PY),
    Rule("code.python-yaml-load", "yaml.load without SafeLoader", "medium", "dangerous-code",
         "yaml.load with the default/unsafe loader can construct arbitrary objects.",
         _r(r"\byaml\.load\s*\((?![^)]*(?:SafeLoader|safe_load|CSafeLoader))"), languages=_PY),
    Rule("code.tls-verify-disabled", "TLS certificate verification disabled", "medium",
         "insecure-transport", "Disabling certificate verification allows man-in-the-middle "
         "attacks.",
         _r(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|"
            r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0|CURLOPT_SSL_VERIFYPEER\s*,\s*(?:false|0)"
            r"|ssl_verify(?:_peer)?\s*[:=]\s*false", re.IGNORECASE)),
    Rule("code.js-eval", "Dynamic code execution (eval/new Function)", "medium",
         "dangerous-code", "eval()/new Function() on untrusted input can lead to code "
         "execution.",
         _r(r"(?<![\w.$])eval\s*\(|\bnew\s+Function\s*\("), languages=_JS),
    Rule("code.js-inner-html", "Raw HTML injection sink", "low", "dangerous-code",
         "Assigning untrusted data to innerHTML / dangerouslySetInnerHTML can cause XSS.",
         _r(r"dangerouslySetInnerHTML|\.(?:inner|outer)HTML\s*=(?!=)|v-html\s*="),
         languages=_JS | frozenset({"HTML"})),
    Rule("code.js-child-process", "Shell command execution", "low", "dangerous-code",
         "child_process exec runs a shell; prefer execFile/spawn with argument arrays.",
         _r(r"\bchild_process\b[^\n]*\bexec(?:Sync)?\s*\(|\bexecSync\s*\("), languages=_JS),
    Rule("code.php-dangerous", "Dangerous PHP function", "medium", "dangerous-code",
         "eval/unserialize/shell execution functions are dangerous with untrusted input.",
         _r(r"(?<![\w>$])(?:eval|unserialize|shell_exec|passthru|system|exec)\s*\("),
         languages=frozenset({"PHP"})),
    Rule("code.cors-wildcard", "Wildcard CORS policy", "low", "configuration",
         "Allowing any origin can expose authenticated endpoints to other sites.",
         _r(r"Access-Control-Allow-Origin['\"]?\s*[:,]\s*['\"]\*['\"]|allow_origins\s*=\s*\[\s*"
            r"['\"]\*['\"]|origin\s*:\s*['\"]\*['\"]")),
    Rule("config.debug-enabled", "Debug mode enabled in settings", "low", "configuration",
         "Debug mode in a committed settings file can leak internals if deployed.",
         _r(r"^\s*DEBUG\s*=\s*True\b"), filenames=("settings.py", "config.py", "production.py")),
    Rule("docker.curl-pipe-shell", "Remote script piped to a shell", "medium", "supply-chain",
         "Piping a downloaded script into a shell runs unverified code at build time.",
         _r(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b")),
    Rule("ci.pull-request-target", "pull_request_target workflow trigger", "medium", "ci",
         "pull_request_target runs with write permissions and secrets; combined with a "
         "checkout of the PR head it can let forks run code with privileges.",
         _r(r"^(?!\s*#).*\bpull_request_target\b"), filenames=(".github/workflows/",)),
    Rule("ci.script-injection", "Untrusted input interpolated into a workflow script", "medium",
         "ci", "Expressions like github.event.*.title/body inside run: steps allow script "
         "injection by anyone who can open an issue or PR.",
         _r(r"\$\{\{\s*github\.event\.(?:issue|pull_request|comment|review|review_comment|"
            r"discussion|pages|commits|head_commit)[\w.\[\]*]*\.(?:title|body|message|name|"
            r"ref|label|email|head_ref)\s*\}\}"), filenames=(".github/workflows/",)),
    Rule("ci.unpinned-action", "Third-party action not pinned to a commit SHA", "info", "ci",
         "Actions referenced by tag or branch can change under you; pinning to a full commit "
         "SHA is the hardened practice.",
         _r(r"uses:\s*(?!actions/|github/|\./|docker://)[\w.-]+/[\w./-]+@(?![0-9a-f]{40}\b)\S+"),
         filenames=(".github/workflows/",)),
    Rule("ci.write-all-permissions", "Workflow grants write-all permissions", "medium", "ci",
         "write-all gives the workflow token broad repository access.",
         _r(r"permissions\s*:\s*write-all"), filenames=(".github/workflows/",)),
]
# fmt: on

_LOCAL_HOST_RE = _r(
    r"^(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\]|[a-z][\w-]*)$", re.IGNORECASE
)


def _connection_string_severity(m: re.Match[str]) -> Severity | None:
    if _PLACEHOLDER_RE.search(m.group("password")):
        return None
    # Single-label hosts (localhost, docker-compose service names) are typically local dev.
    return "low" if _LOCAL_HOST_RE.match(m.group("host")) else "medium"


INSECURE_HTTP_RE = _r(r"\bhttp://(?P<host>[A-Za-z0-9.-]+)(?::\d+)?[^\s'\"<>)]*")
_SAFE_HTTP_HOSTS = _r(
    r"^(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[\w.-]*\.(?:local|localhost|test|example|invalid|"
    r"internal)|(?:www\.)?example\.(?:com|org|net)|[\w.-]*w3\.org|[\w.-]*xmlsoap\.org|"
    r"schemas\.[\w.-]+|purl\.org|json-schema\.org|[\w.-]*apache\.org|xml\.org|ns\.adobe\.com|"
    r"[\w.-]*openxmlformats\.org|java\.sun\.com|xmlns\.[\w.-]+|host\.docker\.internal)$",
    re.IGNORECASE,
)

SENSITIVE_FILES: list[tuple[re.Pattern[str], str, Severity, str]] = [
    (
        _r(r"(^|/)\.env(\.(?!example$|sample$|template$|dist$|defaults?$|test$|ci$)[\w.-]+)?$"),
        "Environment file committed",
        "high",
        "A .env file often contains real credentials and should not be committed.",
    ),
    (
        _r(r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)$"),
        "SSH private key file committed",
        "high",
        "SSH private keys must never be committed.",
    ),
    (
        _r(r"\.(pem|key|p12|pfx|jks|keystore)$", re.IGNORECASE),
        "Key or certificate store committed",
        "medium",
        "Key material may be committed; verify it is not a real private key.",
    ),
    (
        _r(r"(^|/)(terraform\.tfstate(\.backup)?)$"),
        "Terraform state committed",
        "high",
        "Terraform state frequently contains plaintext secrets.",
    ),
    (
        _r(
            r"(^|/)(\.htpasswd|\.pgpass|\.netrc|\.git-credentials|credentials\.json|"
            r"service[-_]?account[\w-]*\.json)$"
        ),
        "Credentials file committed",
        "high",
        "This file type usually stores credentials.",
    ),
    (
        _r(r"\.(sqlite3?|db)$", re.IGNORECASE),
        "Database file committed",
        "low",
        "Committed database files can contain user data or credentials.",
    ),
]
_KEY_FILE_EXCEPTIONS = _r(r"(^|/)(test|tests|fixtures?|testdata|examples?|docs?)/", re.IGNORECASE)

ENV_USAGE_RE = _r(
    r"os\.environ(?:\.get)?\s*[\[(]\s*['\"](?P<a>[A-Z][A-Z0-9_]{1,80})['\"]|"
    r"os\.getenv\(\s*['\"](?P<b>[A-Z][A-Z0-9_]{1,80})['\"]|"
    r"process\.env\.(?P<c>[A-Z][A-Z0-9_]{1,80})|process\.env\[\s*['\"](?P<d>[A-Z][A-Z0-9_]{1,80})|"
    r"import\.meta\.env\.(?P<e>[A-Z][A-Z0-9_]{1,80})|"
    r"System\.getenv\(\s*\"(?P<f>[A-Z][A-Z0-9_]{1,80})\"|"
    r"ENV\[\s*['\"](?P<g>[A-Z][A-Z0-9_]{1,80})['\"]|"
    r"os\.Getenv\(\s*\"(?P<h>[A-Z][A-Z0-9_]{1,80})\"|"
    r"env::var\(\s*\"(?P<i>[A-Z][A-Z0-9_]{1,80})\""
)
_PUBLIC_PREFIXES = (
    "NEXT_PUBLIC_",
    "VITE_",
    "REACT_APP_",
    "NUXT_PUBLIC_",
    "EXPO_PUBLIC_",
    "PUBLIC_",
    "GATSBY_",
)
_SECRET_NAME_RE = _r(r"SECRET|PASSWORD|PASSWD|PRIVATE|TOKEN|API_KEY|APIKEY|ACCESS_KEY|CREDENTIAL")
_PUBLIC_OK_RE = _r(r"PUBLISHABLE|PUBLIC_KEY|ANON_KEY|SITE_KEY|RECAPTCHA|MAPS|ANALYTICS")


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    return -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())


def redact(secret: str) -> str:
    visible = secret[:4] if len(secret) > 8 else ""
    return f"{visible}{'*' * 8}({len(secret)} chars)"


def _redact_all(line: str) -> str:
    out = line
    for rule in SECRET_RULES:
        out = rule.pattern.sub(lambda m: redact(m.group(0)), out)
    return GENERIC_SECRET_RE.sub(
        lambda m: m.group(0).replace(m.group("value"), redact(m.group("value"))), out
    )


def _snippet(line: str) -> str:
    text = _redact_all(line.strip())
    return text if len(text) <= 160 else text[:157] + "..."


def _applies(rule: Rule, path: str, language: str | None) -> bool:
    if rule.filenames is not None:
        name = PurePosixPath(path).name
        return any(
            path.startswith(f) if f.endswith("/") else (name == f or name.startswith(f))
            for f in rule.filenames
        )
    return rule.languages is None or language in rule.languages


def _severity_for(base: Severity, in_test: bool) -> Severity:
    if not in_test:
        return base
    return {"high": "medium", "medium": "low", "low": "info", "info": "info"}[base]  # type: ignore[return-value]


def scan_file(path: str, text: str) -> list[SecurityFinding]:
    cls = classify(path)
    language = cls.language
    in_test = is_test_path(path) or bool(_KEY_FILE_EXCEPTIONS.search(path))
    is_docs = cls.category == FileCategory.DOCUMENTATION
    findings: list[SecurityFinding] = []
    per_rule: Counter[str] = Counter()

    def add(
        rule_id: str,
        title: str,
        severity: Severity,
        confidence: str,
        category: str,
        line_no: int,
        evidence: str,
        description: str,
    ) -> None:
        if per_rule[rule_id] >= MAX_PER_RULE_PER_FILE:
            return
        per_rule[rule_id] += 1
        findings.append(
            SecurityFinding(
                rule=rule_id,
                title=title,
                severity=_severity_for(severity, in_test),
                confidence=confidence,
                category=category,
                path=path,
                line=line_no,  # type: ignore[arg-type]
                evidence=evidence,
                description=description,
                in_test=in_test,
            )
        )

    code_rules = [] if is_docs else [r for r in CODE_RULES if _applies(r, path, language)]
    check_http = cls.category in (FileCategory.SOURCE, FileCategory.CONFIG)
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw[:MAX_LINE_LENGTH]
        for rule in SECRET_RULES:
            m = rule.pattern.search(line)
            if m is None:
                continue
            severity = rule.validator(m) if rule.validator else rule.severity
            if severity is not None:
                add(
                    rule.id,
                    rule.title,
                    severity,
                    rule.confidence,
                    rule.category,
                    number,
                    _snippet(line),
                    rule.description,
                )
        if not is_docs:
            for m in GENERIC_SECRET_RE.finditer(line):
                value = m.group("value")
                if _PLACEHOLDER_RE.search(value) or shannon_entropy(value) < 3.0:
                    continue
                add(
                    "secret.generic-assignment",
                    "Possible hardcoded credential",
                    "medium",
                    "low",
                    "secret",
                    number,
                    _snippet(line),
                    f"A value that looks like a credential is assigned to '{m.group('key')}'.",
                )
        for rule in code_rules:
            if rule.pattern.search(line):
                add(
                    rule.id,
                    rule.title,
                    rule.severity,
                    rule.confidence,
                    rule.category,
                    number,
                    _snippet(line),
                    rule.description,
                )
        if check_http and "http://" in line:
            for m in INSECURE_HTTP_RE.finditer(line):
                if not _SAFE_HTTP_HOSTS.match(m.group("host")):
                    add(
                        "transport.insecure-http",
                        "Insecure HTTP URL",
                        "low",
                        "medium",
                        "insecure-transport",
                        number,
                        _snippet(line),
                        "Plain HTTP traffic can be read or modified in transit; prefer HTTPS.",
                    )
                    break
    if PurePosixPath(path).name.startswith(("Dockerfile", "Containerfile")) or path.endswith(
        ".dockerfile"
    ):
        for line_no, image in unpinned_base_images(text):
            add(
                "docker.unpinned-base-image",
                "Container base image without a pinned version",
                "low",
                "high",
                "supply-chain",
                line_no,
                f"FROM {image}",
                "FROM without a version tag or digest (or with :latest) makes builds "
                "non-reproducible and can pull unexpected changes.",
            )
    return findings


_FROM_RE = _r(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)(?:\s+AS\s+(?P<alias>\S+))?", re.IGNORECASE
)


def unpinned_base_images(text: str) -> list[tuple[int, str]]:
    """FROM lines whose image has no tag/digest or uses :latest. Earlier build-stage names
    and build-arg images are excluded."""
    stages: set[str] = set()
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        m = _FROM_RE.match(line)
        if not m:
            continue
        image = m.group("image")
        name_part = image.rsplit("/", 1)[-1]
        excluded = image.lower() in stages or image == "scratch" or "$" in image or "@" in image
        if not excluded and (":" not in name_part or name_part.endswith(":latest")):
            found.append((number, image))
        if m.group("alias"):
            stages.add(m.group("alias").lower())
    return found


def _sensitive_file_findings(paths: list[str]) -> list[SecurityFinding]:
    findings = []
    for path in paths:
        for pattern, title, severity, description in SENSITIVE_FILES:
            if pattern.search(path):
                in_test = bool(_KEY_FILE_EXCEPTIONS.search(path)) or is_test_path(path)
                findings.append(
                    SecurityFinding(
                        rule="file.sensitive",
                        title=title,
                        severity=_severity_for(severity, in_test),
                        confidence="medium",
                        category="sensitive-file",
                        path=path,
                        description=description,
                        in_test=in_test,
                    )
                )
                break
    return findings


def _gitignore_checks(
    paths: set[str], contents: dict[str, str], uses_env: bool
) -> tuple[list[HygieneCheck], list[SecurityFinding]]:
    checks: list[HygieneCheck] = []
    findings: list[SecurityFinding] = []
    gitignore = contents.get(".gitignore")
    if ".gitignore" not in paths:
        checks.append(
            HygieneCheck(
                key="gitignore",
                label=".gitignore present",
                passed=False,
                detail="No root .gitignore file.",
            )
        )
        if uses_env:
            findings.append(
                SecurityFinding(
                    rule="gitignore.missing",
                    title="No .gitignore file",
                    severity="low",
                    confidence="medium",
                    category="gitignore",
                    path=".gitignore",
                    description="The project reads environment variables but has no .gitignore to "
                    "keep local .env files out of version control.",
                )
            )
        return checks, findings
    checks.append(
        HygieneCheck(
            key="gitignore",
            label=".gitignore present",
            passed=True,
            detail="Root .gitignore found.",
        )
    )
    if gitignore is None:
        return checks, findings
    patterns = [
        ln.strip() for ln in gitignore.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    env_ignored = any(
        re.fullmatch(r"/?(\*\*/)?\.env(\*|\.\*|\.local|\*\.local)?", p)
        or p in {"*.env", ".env*", "**/.env", ".env.*"}
        for p in patterns
    )
    checks.append(
        HygieneCheck(
            key="gitignore_env",
            label=".gitignore excludes .env files",
            passed=env_ignored,
            detail="A .env pattern is present."
            if env_ignored
            else "No pattern excluding .env files was found.",
        )
    )
    if uses_env and not env_ignored:
        findings.append(
            SecurityFinding(
                rule="gitignore.env-not-excluded",
                title=".env files not excluded by .gitignore",
                severity="low",
                confidence="medium",
                category="gitignore",
                path=".gitignore",
                description="The project reads environment variables, but .gitignore has no "
                "pattern for .env files, so local secrets could be committed by "
                "accident.",
            )
        )
    return checks, findings


def all_rules() -> list[SecurityRule]:
    extra = [
        SecurityRule(
            id="secret.generic-assignment",
            title="Possible hardcoded credential",
            severity="medium",
            category="secret",
            description="Credential-like names assigned high-entropy string literals "
            "(placeholders filtered).",
        ),
        SecurityRule(
            id="transport.insecure-http",
            title="Insecure HTTP URL",
            severity="low",
            category="insecure-transport",
            description="http:// URLs in source/config, excluding local, private and "
            "XML-namespace hosts.",
        ),
        SecurityRule(
            id="file.sensitive",
            title="Sensitive file committed",
            severity="high",
            category="sensitive-file",
            description="Committed .env files, private keys, credential stores, "
            "Terraform state and database files.",
        ),
        SecurityRule(
            id="env.client-exposed-secret",
            title="Secret-like variable exposed to the client bundle",
            severity="medium",
            category="env-exposure",
            description="Public-prefixed env vars (NEXT_PUBLIC_, VITE_, ...) whose "
            "names suggest secrets.",
        ),
        SecurityRule(
            id="docker.unpinned-base-image",
            title="Container base image without a pinned version",
            severity="low",
            category="supply-chain",
            description="Dockerfile FROM lines without a tag/digest or using :latest "
            "(multi-stage aliases and build args excluded).",
        ),
        SecurityRule(
            id="gitignore.env-not-excluded",
            title=".env not excluded by .gitignore",
            severity="low",
            category="gitignore",
            description="Env vars are used but .gitignore has no .env pattern.",
        ),
    ]
    return [
        SecurityRule(
            id=r.id,
            title=r.title,
            severity=r.severity,
            category=r.category,
            description=r.description,
        )
        for r in SECRET_RULES + CODE_RULES
    ] + extra


def analyze_security(
    tree: RepositoryTree, contents: dict[str, str], has_lockfiles: bool
) -> SecurityAnalysis:
    all_paths = [e.path for e in tree.files() if ignored_segment(e.path) is None]
    path_set = set(all_paths)
    findings = _sensitive_file_findings(all_paths)
    env_vars: set[str] = set()
    env_files = 0
    scanned = 0

    for path, text in contents.items():
        cls = classify(path)
        if cls.category in (FileCategory.BINARY, FileCategory.ASSET, FileCategory.LOCKFILE):
            continue
        scanned += 1
        findings.extend(scan_file(path, text))
        if cls.category in (FileCategory.SOURCE, FileCategory.CONFIG, FileCategory.TEST):
            names = {next(g for g in m.groups() if g) for m in ENV_USAGE_RE.finditer(text)}
            if names:
                env_files += 1
                env_vars |= names

    for name in sorted(env_vars):
        if (
            name.startswith(_PUBLIC_PREFIXES)
            and _SECRET_NAME_RE.search(name)
            and not _PUBLIC_OK_RE.search(name)
        ):
            findings.append(
                SecurityFinding(
                    rule="env.client-exposed-secret",
                    title="Secret-like variable exposed to the client bundle",
                    severity="medium",
                    confidence="medium",
                    category="env-exposure",
                    path="(multiple files)",
                    evidence=name,
                    description=f"{name} uses a public prefix, so bundlers inline its value into "
                    "client-side code, yet its name suggests a secret.",
                )
            )

    hygiene, gitignore_findings = _gitignore_checks(path_set, contents, bool(env_vars))
    findings.extend(gitignore_findings)
    security_policy = next(
        (
            p
            for p in all_paths
            if PurePosixPath(p).name.lower() in {"security.md", "security.rst", "security.txt"}
            and p.count("/") <= 1
        ),
        None,
    )
    dependency_bot = next(
        (
            p
            for p in all_paths
            if p
            in {
                ".github/dependabot.yml",
                ".github/dependabot.yaml",
                "renovate.json",
                ".renovaterc",
                ".renovaterc.json",
                ".github/renovate.json",
                "renovate.json5",
            }
        ),
        None,
    )
    codeowners = next((p for p in all_paths if PurePosixPath(p).name == "CODEOWNERS"), None)
    hygiene += [
        HygieneCheck(
            key="security_policy",
            label="Security policy",
            passed=bool(security_policy),
            detail=security_policy or "No SECURITY.md found.",
        ),
        HygieneCheck(
            key="dependency_updates",
            label="Automated dependency updates",
            passed=bool(dependency_bot),
            detail=dependency_bot or "No Dependabot or Renovate configuration.",
        ),
        HygieneCheck(
            key="lockfiles",
            label="Dependency lockfile",
            passed=has_lockfiles,
            detail="Lockfile present." if has_lockfiles else "No lockfile found.",
        ),
        HygieneCheck(
            key="codeowners",
            label="CODEOWNERS",
            passed=bool(codeowners),
            detail=codeowners or "No CODEOWNERS file.",
        ),
    ]

    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.category, f.path, f.line or 0))
    return SecurityAnalysis(
        disclaimer=DISCLAIMER,
        findings=findings[:MAX_FINDINGS],
        findings_truncated=len(findings) > MAX_FINDINGS,
        counts_by_severity={s: sum(f.severity == s for f in findings) for s in _SEVERITY_ORDER},
        counts_by_category=dict(sorted(Counter(f.category for f in findings).items())),
        files_scanned=scanned,
        env_variables=sorted(env_vars)[:150],
        env_variable_files=env_files,
        hygiene=hygiene,
        rules=all_rules(),
        coverage_note=f"Content checks ran on {scanned} downloaded files; path-based checks ran "
        f"on all {len(all_paths)} files.",
    )
