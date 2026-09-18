import pytest

from app.analyzers.structure import analyze_structure
from app.services.repository_tree import RepositoryTree, TreeEntry, build_tree, is_safe_path


def _tree(files: dict[str, int], dirs: list[str] | None = None, **extra: object) -> RepositoryTree:
    entries = [TreeEntry(path=d, type="dir") for d in dirs or []]
    entries += [TreeEntry(path=p, type="file", size=s) for p, s in files.items()]
    return RepositoryTree(commit_sha="abc", entries=entries, **extra)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    [
        "../etc/passwd",
        "a/../../b",
        "/abs/path",
        "a//b",
        "a/./b",
        "win\\path",
        "bad\x00name",
        "new\nline",
        "",
        "x" * 2000,
        None,
        42,
    ],
)
def test_unsafe_paths_are_rejected(path: object) -> None:
    assert not is_safe_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/main.py",
        ".github/workflows/ci.yml",
        "a b/c d.txt",
        "unicode/名前.md",
        "dots..in..name.txt",
    ],
)
def test_safe_paths_are_accepted(path: str) -> None:
    assert is_safe_path(path)


def test_build_tree_sanitizes_and_limits() -> None:
    raw = [
        {"path": "src", "type": "tree", "mode": "040000"},
        {"path": "src/a.py", "type": "blob", "mode": "100644", "size": 10},
        {"path": "../escape.py", "type": "blob", "mode": "100644", "size": 5},
        {"path": "link", "type": "blob", "mode": "120000", "size": 7},
        {"path": "libs/sub", "type": "commit", "mode": "160000"},
        {"path": "weird", "type": "tag"},
        "not-a-dict",
        {"path": "src/b.py", "type": "blob", "mode": "100644", "size": -3},
        {"path": "src/c.py", "type": "blob", "mode": "100644", "size": 1},
    ]
    tree = build_tree("sha1", raw, github_truncated=False, max_entries=5)
    assert [e.type for e in tree.entries] == ["dir", "file", "symlink", "submodule", "file"]
    assert tree.entries[-1].size == 0  # negative size coerced
    assert tree.unsafe_paths_skipped == 1
    assert tree.truncated_by_limit and tree.truncated
    assert any("unsafe" in n for n in tree.notes)


def test_structure_counts_and_ignored_directories() -> None:
    tree = _tree(
        {
            "README.md": 1_000,
            "src/app/main.py": 5_000,
            "src/app/util.py": 2_000,
            "tests/test_main.py": 1_500,
            "node_modules/react/index.js": 90_000,
            "node_modules/react/cjs/react.js": 10_000,
            "web/dist/bundle.js": 50_000,
            "assets/logo.png": 30_000,
            "build": 10,  # a *file* named build is not an ignored directory
        },
        dirs=[
            "src",
            "src/app",
            "tests",
            "node_modules",
            "node_modules/react",
            "web",
            "web/dist",
            "assets",
        ],
    )
    s = analyze_structure(tree, repo_name="demo", max_file_bytes=20_000)

    assert s.total_files == 9
    assert s.analyzed_files == 6
    assert s.ignored_files == 3
    assert s.ignored_size_bytes == 150_000
    assert {d.path: d.files for d in s.ignored_directories} == {"node_modules": 2, "web/dist": 1}
    assert s.total_directories == 5  # src, src/app, tests, web, assets (ignored excluded)
    assert s.oversized_files == 1  # logo.png > 20k
    assert s.max_depth == 3

    categories = {c.category: c.files for c in s.categories}
    assert categories == {"source": 2, "test": 1, "documentation": 1, "asset": 1, "other": 1}
    assert s.largest_files[0].path == "assets/logo.png"
    assert s.largest_directories[0].path in {"assets", "src"}


def test_tree_marks_ignored_nodes_and_sorts_dirs_first() -> None:
    tree = _tree({"z.txt": 1, "src/a.py": 2, "node_modules/x/y.js": 3})
    s = analyze_structure(tree, repo_name="demo", max_file_bytes=10_000)
    names = [c.name for c in s.tree.children or []]
    assert names == ["node_modules", "src", "z.txt"]
    nm = s.tree.children[0]  # type: ignore[index]
    assert nm.ignored and nm.children is None and nm.files == 1 and nm.size == 3
    src = s.tree.children[1]  # type: ignore[index]
    assert src.files == 1 and src.size == 2
    assert s.tree.files == 3  # root aggregates everything on disk, ignored included
    assert [t.name for t in s.top_level] == names
    assert all(t.children is None for t in s.top_level)


def test_tree_node_budget_is_breadth_first() -> None:
    files = {f"d{i}/f{j}.py": 1 for i in range(10) for j in range(10)}
    s = analyze_structure(_tree(files), repo_name="demo", max_file_bytes=10_000, node_budget=15)
    root_children = s.tree.children or []
    assert len(root_children) == 10  # the whole first level fits before any second level
    shown = sum(len(c.children or []) for c in root_children)
    omitted = sum(c.omitted_children for c in root_children)
    assert shown == 5 and shown + omitted == 100


def test_symlinks_and_submodules_are_counted_not_sized() -> None:
    tree = RepositoryTree(
        commit_sha="x",
        entries=[
            TreeEntry("a.py", "file", 10),
            TreeEntry("link", "symlink"),
            TreeEntry("vendor-lib", "submodule"),
        ],
    )
    s = analyze_structure(tree, repo_name="demo", max_file_bytes=100)
    assert s.symlinks == 1
    assert s.submodules == ["vendor-lib"]
    assert s.total_files == 1
