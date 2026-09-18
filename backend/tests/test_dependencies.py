import pytest

from app.analyzers.dependency_analyzer import analyze_dependencies, classify_constraint
from app.analyzers.dependency_parsers import (
    ManifestParseError,
    ParsedDependency,
    parse_cargo,
    parse_composer,
    parse_gemfile,
    parse_go_mod,
    parse_gradle,
    parse_package_json,
    parse_pipfile,
    parse_pom,
    parse_pyproject,
    parse_requirements,
    parse_setup_cfg,
    parser_for,
)
from app.services.repository_tree import RepositoryTree, TreeEntry


def by_name(deps: list[ParsedDependency]) -> dict[str, ParsedDependency]:
    return {d.name: d for d in deps}


def test_package_json_sections_and_sources() -> None:
    deps = by_name(
        parse_package_json("""{
      "name": "web",
      "dependencies": {"react": "^19.0.0", "lodash": "4.17.21", "mylib": "file:../mylib",
                       "fork": "github:user/fork#main", "shared": "workspace:*"},
      "devDependencies": {"typescript": "~5.6.0"},
      "peerDependencies": {"react-dom": ">=18"},
      "optionalDependencies": {"fsevents": "*"}
    }""")
    )
    assert deps["react"].scope == "production" and deps["react"].version == "^19.0.0"
    assert deps["typescript"].scope == "development"
    assert deps["react-dom"].scope == "peer"
    assert deps["fsevents"].scope == "optional"
    assert deps["mylib"].source == "path"
    assert deps["fork"].source == "git"


@pytest.mark.parametrize(
    "bad", ["{not json", "[1, 2]", "[" * 100_000], ids=["broken", "array", "deep"]
)
def test_package_json_malformed(bad: str) -> None:
    with pytest.raises(ManifestParseError):
        parse_package_json(bad)


def test_requirements_txt() -> None:
    text = """
    # core
    Django>=4.2,<5  # web framework
    requests[security]==2.32.3
    numpy ; python_version >= "3.10"
    -r base.txt
    --index-url https://pypi.org/simple
    -e git+https://github.com/org/pkg.git#egg=pkg
    https://example.com/wheel.whl#egg=wheelpkg
    flask==3.0.0 --hash=sha256:abc
    """
    deps = by_name(parse_requirements(text, "requirements.txt"))
    assert deps["Django"].version == ">=4.2,<5"
    assert deps["requests"].version == "==2.32.3"
    assert deps["numpy"].version is None
    assert deps["pkg"].source == "git"
    assert deps["wheelpkg"].source == "url"
    assert deps["flask"].version == "==3.0.0"
    assert all(d.scope == "production" for d in deps.values())
    assert parse_requirements("pytest\n", "requirements-dev.txt")[0].scope == "development"
    assert parse_requirements("pytest\n", "requirements/test.txt")[0].scope == "development"


def test_pyproject_pep621_poetry_and_groups() -> None:
    deps = parse_pyproject("""
[project]
name = "x"
dependencies = ["fastapi>=0.115", "pydantic==2.8.0", "mylib @ git+https://github.com/o/r"]
[project.optional-dependencies]
dev = ["pytest>=8"]
postgres = ["asyncpg"]
[dependency-groups]
lint = ["ruff"]
[tool.poetry.dependencies]
python = "^3.11"
httpx = "^0.27"
boto3 = {version = "^1.34", optional = true}
local = {path = "../local"}
[tool.poetry.group.test.dependencies]
hypothesis = "*"
""")
    d = by_name(deps)
    assert d["fastapi"].scope == "production" and d["fastapi"].version == ">=0.115"
    assert d["mylib"].source == "git"
    assert d["pytest"].scope == "development"
    assert d["asyncpg"].scope == "optional"
    assert d["ruff"].scope == "development"
    assert "python" not in d
    assert d["httpx"].version == "^0.27"
    assert d["boto3"].scope == "optional"
    assert d["local"].source == "path"
    assert d["hypothesis"].scope == "development"


def test_pyproject_invalid_toml() -> None:
    with pytest.raises(ManifestParseError):
        parse_pyproject("[project\nname=")


def test_pipfile_and_setup_cfg() -> None:
    pip = by_name(parse_pipfile('[packages]\nrequests = "*"\n[dev-packages]\nblack = "==24.1"\n'))
    assert pip["requests"].scope == "production" and pip["black"].scope == "development"
    cfg = by_name(
        parse_setup_cfg("""
[options]
install_requires =
    click>=8
    rich
[options.extras_require]
testing = pytest
""")
    )
    assert cfg["click"].version == ">=8" and cfg["rich"].scope == "production"
    assert cfg["pytest"].scope == "development"


def test_pom_resolves_properties_and_scopes() -> None:
    deps = by_name(
        parse_pom("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <version>1.0.0</version>
  <properties><spring.version>6.1.2</spring.version></properties>
  <dependencyManagement><dependencies><dependency>
    <groupId>managed</groupId><artifactId>only</artifactId><version>9</version>
  </dependency></dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>org.springframework</groupId><artifactId>spring-core</artifactId>
      <version>${spring.version}</version></dependency>
    <dependency><groupId>junit</groupId><artifactId>junit</artifactId>
      <version>4.13.2</version><scope>test</scope></dependency>
    <dependency><groupId>com.x</groupId><artifactId>bom-managed</artifactId></dependency>
    <dependency><groupId>com.x</groupId><artifactId>unknown-prop</artifactId>
      <version>${missing}</version><optional>true</optional></dependency>
  </dependencies>
</project>""")
    )
    assert deps["org.springframework:spring-core"].version == "6.1.2"
    assert deps["junit:junit"].scope == "development"
    assert deps["com.x:bom-managed"].version is None
    assert deps["com.x:unknown-prop"].version == "${missing}"
    assert deps["com.x:unknown-prop"].scope == "optional"
    assert "managed:only" not in deps


def test_pom_rejects_entity_expansion() -> None:
    bomb = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<project><dependencies>&lol2;</dependencies></project>"""
    with pytest.raises(ManifestParseError):
        parse_pom(bomb)


def test_pom_rejects_external_entities() -> None:
    xxe = """<?xml version="1.0"?>
<!DOCTYPE p [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><project>&xxe;</project>"""
    with pytest.raises(ManifestParseError):
        parse_pom(xxe)


def test_gradle_groovy_and_kotlin() -> None:
    groovy = """
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.2.0'
    implementation "com.google.guava:guava:$guavaVersion"
    testImplementation group: 'junit', name: 'junit', version: '4.13.2'
    compileOnly 'org.projectlombok:lombok'
    implementation libs.okhttp
}"""
    d = by_name(parse_gradle(groovy))
    assert d["org.springframework.boot:spring-boot-starter-web"].version == "3.2.0"
    assert d["com.google.guava:guava"].version == "$guavaVersion"
    assert d["junit:junit"].scope == "development"
    assert d["org.projectlombok:lombok"].scope == "build"
    assert d["org.projectlombok:lombok"].version is None
    assert len(d) == 4  # catalog alias is not guessed

    kts = (
        'dependencies {\n  implementation("io.ktor:ktor-server-core:2.3.7")\n'
        '  testImplementation(kotlin("test"))\n}'
    )
    k = by_name(parse_gradle(kts))
    assert k == {
        "io.ktor:ktor-server-core": ParsedDependency(
            "io.ktor:ktor-server-core", "2.3.7", "production"
        )
    }


def test_cargo() -> None:
    d = by_name(
        parse_cargo("""
[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "=1.36.0"
local = { path = "../local" }
maybe = { version = "0.3", optional = true }
[dev-dependencies]
criterion = "0.5"
[build-dependencies]
cc = "1"
[target.'cfg(windows)'.dependencies]
winapi = "0.3"
""")
    )
    assert d["serde"].version == "1.0" and d["serde"].scope == "production"
    assert d["local"].source == "path"
    assert d["maybe"].scope == "optional"
    assert d["criterion"].scope == "development"
    assert d["cc"].scope == "build"
    assert "winapi" in d


def test_go_mod() -> None:
    deps = by_name(
        parse_go_mod("""module github.com/o/app

go 1.22

require github.com/single/dep v1.0.0

require (
    github.com/gin-gonic/gin v1.9.1
    golang.org/x/sys v0.15.0 // indirect
)
""")
    )
    assert deps["github.com/single/dep"].version == "v1.0.0"
    assert deps["github.com/gin-gonic/gin"].direct is True
    assert deps["golang.org/x/sys"].direct is False


def test_composer_skips_platform_requirements() -> None:
    d = by_name(
        parse_composer("""{"require": {"php": ">=8.1", "ext-json": "*",
        "laravel/framework": "^11.0"}, "require-dev": {"phpunit/phpunit": "^10"}}""")
    )
    assert set(d) == {"laravel/framework", "phpunit/phpunit"}
    assert d["phpunit/phpunit"].scope == "development"


def test_gemfile_groups() -> None:
    d = by_name(
        parse_gemfile("""
source "https://rubygems.org"
gem "rails", "~> 7.1.0"
gem "pg", ">= 1.1", "< 2.0"
gem "internal", git: "https://github.com/o/internal"
group :development, :test do
  gem "rspec-rails"
end
gem "rubocop", require: false, group: :development
gem "puma"
""")
    )
    assert d["rails"].version == "~> 7.1.0" and d["rails"].scope == "production"
    assert d["pg"].version == ">= 1.1, < 2.0"
    assert d["internal"].source == "git"
    assert d["rspec-rails"].scope == "development"
    assert d["rubocop"].scope == "development"
    assert d["puma"].scope == "production"


@pytest.mark.parametrize(
    ("path", "ecosystem"),
    [
        ("package.json", "npm"),
        ("svc/requirements-test.txt", "PyPI"),
        ("pom.xml", "Maven"),
        ("app/build.gradle.kts", "Maven"),
        ("Cargo.toml", "crates.io"),
        ("go.mod", "Go"),
        ("composer.json", "Packagist"),
        ("Gemfile", "RubyGems"),
        ("Pipfile", "PyPI"),
    ],
)
def test_parser_registry(path: str, ecosystem: str) -> None:
    found = parser_for(path)
    assert found is not None and found[0] == ecosystem


@pytest.mark.parametrize(
    ("version", "ecosystem", "expected"),
    [
        ("==2.0.1", "PyPI", "exact"),
        (">=2", "PyPI", "range"),
        (None, "PyPI", "none"),
        ("4.17.21", "npm", "exact"),
        ("^4.17.21", "npm", "range"),
        ("*", "npm", "none"),
        ("latest", "npm", "none"),
        ("v1.2.3", "Go", "exact"),
        ("1.0", "crates.io", "range"),
        ("=1.0.3", "crates.io", "exact"),
        (None, "Maven", "managed"),
        ("${x}", "Maven", "managed"),
        ("[1.0,2.0)", "Maven", "range"),
        ("1.2.3", "Maven", "exact"),
        ("~> 7.1", "RubyGems", "range"),
    ],
)
def test_constraint_classification(version: str | None, ecosystem: str, expected: str) -> None:
    assert classify_constraint(ParsedDependency("x", version, "production"), ecosystem) == expected


def test_analyze_dependencies_aggregates_manifests() -> None:
    files = {
        "package.json": '{"dependencies": {"react": "^19.0.0"}, '
        '"devDependencies": {"vitest": "*"}}',
        "apps/admin/package.json": '{"dependencies": {"react": "^18.2.0"}}',
        "package-lock.json": "{}",
        "api/requirements.txt": "fastapi==0.115.0\n",
        "api/pyproject.toml": "[project\nbroken",
        "node_modules/x/package.json": '{"dependencies": {"evil": "1"}}',
        "huge/pom.xml": None,  # present in tree, not downloaded
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", 10) for p in files])
    contents = {p: t for p, t in files.items() if t is not None}
    result = analyze_dependencies(tree, contents)

    assert result.total == 4
    assert result.production == 3 and result.development == 1
    assert result.unconstrained == 1  # vitest "*"
    assert result.unique_packages == 3
    assert result.lockfiles == ["package-lock.json"]
    eco = {e.ecosystem: e for e in result.ecosystems}
    assert eco["npm"].has_lockfile and not eco["PyPI"].has_lockfile
    assert [c.name for c in result.version_conflicts] == ["react"]
    assert result.version_conflicts[0].versions == ["^18.2.0", "^19.0.0"]
    broken = next(m for m in result.manifests if m.path == "api/pyproject.toml")
    assert broken.parse_error and "TOML" in broken.parse_error
    assert result.manifests_not_analyzed == ["huge/pom.xml"]
    assert all(d.manifest != "node_modules/x/package.json" for d in result.dependencies)
    assert "vulnerability database" in result.vulnerability_data
