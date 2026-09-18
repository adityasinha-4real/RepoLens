from app.analyzers.code_analyzer import (
    analyze_code,
    brace_heuristic,
    count_commented_code,
    detect_tooling,
    find_markers,
    python_function_complexity,
)
from app.services.repository_tree import RepositoryTree, TreeEntry


def test_markers_only_in_comments() -> None:
    text = "\n".join(
        [
            "x = 1  # TODO: remove this hack",
            "todoList = []",  # identifier, not a marker
            "msg = 'TODO in a string without comment'",
            "// FIXME(alice) handle null",
            "/* HACK */",
            "  * XXX legacy path",
            "<!-- TODO translate -->",
        ]
    )
    items = find_markers("a.py", text)
    assert [(i.line, i.tag) for i in items] == [
        (1, "TODO"),
        (4, "FIXME"),
        (5, "HACK"),
        (6, "XXX"),
        (7, "TODO"),
    ]
    assert items[0].text == "TODO: remove this hack"
    assert items[4].text == "TODO: translate"


def test_commented_code_needs_a_run_of_code_like_lines() -> None:
    js = "\n".join(
        [
            "// This explains the function below.",
            "// const x = compute(a, b);",
            "// if (x > 3) {",
            "//   return x;",
            "// }",
            "function f() {}",
            "// single = 1;",  # isolated line: not counted
        ]
    )
    assert count_commented_code(js, "JavaScript") == 4
    prose = "# This module handles parsing.\n# It is fast and small.\n"
    assert count_commented_code(prose, "Python") == 0
    assert count_commented_code("# x = 1\n# y = 2\n", None) == 0  # unknown comment syntax


def test_python_mccabe_complexity() -> None:
    code = """
def simple():
    return 1

def branchy(a, b):
    if a and b:          # +1 if, +1 and
        pass
    elif a or b or a:    # +1 elif, +2 or
        pass
    for i in range(3):   # +1
        while i:         # +1
            i -= 1
    try:
        pass
    except ValueError:   # +1
        pass
    return [x for x in range(3) if x]  # +2 comprehension + if

class Service:
    def method(self):
        def inner():
            if True:
                pass
        return inner
"""
    items = {i.name: i for i in python_function_complexity("m.py", code) or []}
    assert items["simple"].complexity == 1
    assert items["branchy"].complexity == 11
    assert items["Service.method"].complexity == 1  # nested def not counted in parent
    assert items["Service.method.inner"].complexity == 2
    assert items["branchy"].length == 13 and items["branchy"].line == 5


def test_python_complexity_tolerates_invalid_or_hostile_code() -> None:
    assert python_function_complexity("bad.py", "def f(:\n") is None
    assert python_function_complexity("deep.py", "x = " + "(" * 50_000 + ")" * 50_000) is None


def test_brace_heuristic_ignores_strings_and_comments() -> None:
    code = 'if (a && b) { while (x) { if (y) { } } }\n// if if if\nconst s = "if for while";\n'
    item = brace_heuristic("a.ts", code)
    assert item.complexity == 4  # if, &&, while, if
    assert item.max_nesting == 3


def test_tooling_detection() -> None:
    paths = [
        ".github/workflows/ci.yml",
        ".eslintrc.json",
        "tsconfig.json",
        ".prettierrc",
        "pyproject.toml",
        ".editorconfig",
        ".pre-commit-config.yaml",
        "pkg/x_test.go",
        "vitest.config.ts",
    ]
    contents = {"pyproject.toml": "[tool.ruff]\nline-length=100\n[tool.mypy]\nstrict=true\n"}
    t = detect_tooling(paths, contents, {"pytest", "jest"})
    assert t.ci == ["GitHub Actions"]
    assert {"ESLint", "Ruff"} <= set(t.linters)
    assert "Prettier" in t.formatters
    assert set(t.type_checkers) == {"TypeScript", "mypy"}
    assert {"pytest", "Jest", "Vitest", "Go testing"} <= set(t.test_frameworks)
    assert t.pre_commit and t.editorconfig


def test_analyze_code_end_to_end() -> None:
    long_py = "\n".join(f"x{i} = {i}" for i in range(600))
    complex_py = "def f(a):\n" + "".join(f"    if a == {i}:\n        pass\n" for i in range(12))
    files = {
        "src/long.py": long_py,
        "src/complex.py": complex_py + "# TODO: simplify\n",
        "src/big_unfetched.js": None,
        "tests/test_long.py": "def test_x():\n    assert True\n",
        "README.md": "TODO: write docs",  # docs are not scanned for markers
        "node_modules/x/index.js": "// TODO vendored",
    }
    sizes = {"src/big_unfetched.js": 40_000}
    tree = RepositoryTree(
        "sha", [TreeEntry(p, "file", sizes.get(p, len(t or ""))) for p, t in files.items()]
    )
    contents = {p: t for p, t in files.items() if t is not None}
    q = analyze_code(tree, contents, set())

    assert q.source_files == 3 and q.test_files == 1
    assert q.test_to_source_ratio == round(1 / 3, 3)
    assert q.sampled_source_files == 2
    assert {f.path: f.estimated for f in q.long_files} == {
        "src/long.py": False,
        "src/big_unfetched.js": True,
    }
    assert q.long_file_count == 2
    assert q.marker_counts["TODO"] == 1 and q.markers[0].path == "src/complex.py"
    assert q.high_complexity_count == 1
    assert q.complexity_hotspots[0].name == "f" and q.complexity_hotspots[0].complexity == 13
    assert q.python_functions_analyzed == 2
    assert "2 of 3" in q.coverage_note
