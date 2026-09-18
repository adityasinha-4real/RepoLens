import pytest

from app.analyzers.file_classifier import (
    FileCategory,
    classify,
    detect_language,
    ignored_segment,
    is_test_path,
)


@pytest.mark.parametrize(
    ("path", "segment"),
    [
        ("node_modules/react/index.js", "node_modules"),
        ("web/node_modules/x/y.js", "node_modules"),
        ("dist/app.js", "dist"),
        ("pkg/__pycache__/mod.cpython-312.pyc", "__pycache__"),
        (".venv/lib/site.py", ".venv"),
        ("vendor/github.com/pkg/errors/errors.go", "vendor"),
        ("target/debug/app", "target"),
        ("coverage/lcov.info", "coverage"),
    ],
)
def test_ignored_directories(path: str, segment: str) -> None:
    assert ignored_segment(path) == segment


@pytest.mark.parametrize(
    "path",
    ["src/build.py", "build", "scripts/dist", "src/builder/index.ts", "Distribution/main.c"],
)
def test_similar_names_are_not_ignored(path: str) -> None:
    assert ignored_segment(path) is None


@pytest.mark.parametrize(
    ("path", "category", "language"),
    [
        ("src/app/main.py", FileCategory.SOURCE, "Python"),
        ("lib/index.tsx", FileCategory.SOURCE, "TypeScript"),
        ("cmd/server/main.go", FileCategory.SOURCE, "Go"),
        ("tests/test_api.py", FileCategory.TEST, "Python"),
        ("src/utils/date.test.ts", FileCategory.TEST, "TypeScript"),
        ("pkg/handler_test.go", FileCategory.TEST, "Go"),
        ("src/test/java/com/x/UserServiceTest.java", FileCategory.TEST, "Java"),
        ("app/__tests__/Button.jsx", FileCategory.TEST, "JavaScript"),
        ("README.md", FileCategory.DOCUMENTATION, "Markdown"),
        ("docs/guide/intro.mdx", FileCategory.DOCUMENTATION, "MDX"),
        ("LICENSE", FileCategory.DOCUMENTATION, None),
        ("package-lock.json", FileCategory.LOCKFILE, "JSON"),
        ("go.sum", FileCategory.LOCKFILE, None),
        ("assets/logo.png", FileCategory.ASSET, None),
        ("public/icon.svg", FileCategory.ASSET, None),
        ("release/app.exe", FileCategory.BINARY, None),
        ("static/js/app.min.js", FileCategory.GENERATED, "JavaScript"),
        ("api/service_pb2.py", FileCategory.GENERATED, "Python"),
        ("Dockerfile", FileCategory.CONFIG, "Dockerfile"),
        ("docker/Dockerfile.prod", FileCategory.CONFIG, "Dockerfile"),
        ("next.config.ts", FileCategory.CONFIG, "TypeScript"),
        (".github/workflows/ci.yml", FileCategory.CONFIG, "YAML"),
        ("pyproject.toml", FileCategory.CONFIG, "TOML"),
        (".gitignore", FileCategory.CONFIG, None),
        ("fixtures/users.json", FileCategory.DATA, "JSON"),
    ],
)
def test_classify(path: str, category: FileCategory, language: str | None) -> None:
    result = classify(path)
    assert result.category == category
    assert result.language == language


def test_detect_language_special_filenames() -> None:
    assert detect_language("Makefile") == "Makefile"
    assert detect_language("build/CMakeLists.txt") == "CMake"
    assert detect_language("Gemfile") == "Ruby"
    assert detect_language("script.R") == "R"
    assert detect_language("notes.unknownext") is None


def test_test_detection_is_not_fooled_by_substrings() -> None:
    assert not is_test_path("src/contest/solver.py")
    assert not is_test_path("src/attestation.py")
    assert is_test_path("spec/models/user_spec.rb")
