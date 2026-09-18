"""Repository structure: sizes, categories, ignored directories and a bounded tree for the UI."""

from __future__ import annotations

import heapq
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from app.analyzers.file_classifier import IGNORED_DIRS, classify
from app.schemas.structure import (
    CategoryStat,
    DirectoryStat,
    FileStat,
    StructureAnalysis,
    TreeNode,
)
from app.services.repository_tree import RepositoryTree

TREE_NODE_BUDGET = 3000
LARGEST_LIMIT = 15


@dataclass
class _Node:
    name: str
    path: str
    type: str
    size: int = 0
    files: int = 0
    ignored: bool = False
    children: dict[str, _Node] = field(default_factory=dict)


def _ignored_root(path: str, *, is_dir: bool) -> str | None:
    """Path of the outermost ignored directory containing `path` (or equal to it, for dirs).

    A *file* named like an ignored directory (e.g. a script called `build`) is not ignored."""
    parts = path.split("/")
    for i, segment in enumerate(parts if is_dir else parts[:-1]):
        if segment in IGNORED_DIRS:
            return "/".join(parts[: i + 1])
    return None


def _insert(root: _Node, path: str, type_: str, size: int) -> None:
    parts = path.split("/")
    node = root
    for i, part in enumerate(parts[:-1]):
        child = node.children.get(part)
        if child is None:
            child = _Node(part, "/".join(parts[: i + 1]), "dir")
            node.children[part] = child
        node = child
    leaf = node.children.get(parts[-1])
    if leaf is None:
        node.children[parts[-1]] = _Node(parts[-1], path, type_, size)
    elif type_ != "dir":  # a later file entry overrides an implicit dir with the same name
        leaf.type, leaf.size = type_, size


def _aggregate(node: _Node) -> tuple[int, int]:
    if node.type == "file":
        return node.size, 1
    if node.type != "dir":
        return 0, 0
    size = files = 0
    for child in node.children.values():
        s, f = _aggregate(child)
        size += s
        files += f
    if not node.ignored:
        node.size, node.files = size, files
    return node.size, node.files


def _sorted_children(node: _Node) -> list[_Node]:
    return sorted(node.children.values(), key=lambda n: (n.type != "dir", n.name.lower()))


def _to_tree(root: _Node, budget: int) -> TreeNode:
    """Breadth-first serialization so shallow levels are always complete before deep ones."""
    out_root = TreeNode(
        name=root.name, path="", type="dir", size=root.size, files=root.files, children=[]
    )
    queue: deque[tuple[_Node, TreeNode]] = deque([(root, out_root)])
    remaining = budget
    while queue:
        node, out = queue.popleft()
        assert out.children is not None
        for child in _sorted_children(node):
            if remaining <= 0:
                out.omitted_children += 1
                continue
            remaining -= 1
            is_dir = child.type == "dir"
            out_child = TreeNode(
                name=child.name,
                path=child.path,
                type=child.type,  # type: ignore[arg-type]
                size=child.size,
                files=child.files,
                ignored=child.ignored,
                children=[] if is_dir and not child.ignored else None,
            )
            out.children.append(out_child)
            if is_dir and not child.ignored:
                queue.append((child, out_child))
    return out_root


def analyze_structure(
    tree: RepositoryTree,
    *,
    repo_name: str,
    max_file_bytes: int,
    node_budget: int = TREE_NODE_BUDGET,
) -> StructureAnalysis:
    root = _Node(repo_name, "", "dir")
    ignored_dirs: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # path -> [files, bytes]
    category_files: Counter[str] = Counter()
    category_bytes: Counter[str] = Counter()
    dir_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sizes: list[tuple[int, str]] = []

    total_files = total_bytes = analyzed_files = analyzed_bytes = 0
    directories = symlinks = oversized = max_depth = 0
    submodules: list[str] = []

    for entry in tree.entries:
        ignored_at = _ignored_root(entry.path, is_dir=entry.type == "dir")
        if entry.type == "dir":
            if ignored_at is None:
                directories += 1
                _insert(root, entry.path, "dir", 0)
            else:
                ignored_dirs.setdefault(ignored_at, [0, 0])
                _insert(root, ignored_at, "dir", 0)
            continue
        if entry.type == "submodule":
            submodules.append(entry.path)
        if entry.type == "symlink":
            symlinks += 1

        if entry.type == "file":
            total_files += 1
            total_bytes += entry.size
        if ignored_at is not None:
            if entry.type == "file":
                stat = ignored_dirs[ignored_at]
                stat[0] += 1
                stat[1] += entry.size
            _insert(root, ignored_at, "dir", 0)
            continue

        _insert(root, entry.path, entry.type, entry.size)
        max_depth = max(max_depth, entry.path.count("/") + 1)
        if entry.type != "file":
            continue

        analyzed_files += 1
        analyzed_bytes += entry.size
        if entry.size > max_file_bytes:
            oversized += 1
        cls = classify(entry.path)
        category_files[cls.category] += 1
        category_bytes[cls.category] += entry.size
        sizes.append((entry.size, entry.path))
        parts = entry.path.split("/")
        for i in range(1, len(parts)):
            stat = dir_stats["/".join(parts[:i])]
            stat[0] += 1
            stat[1] += entry.size

    # Mark ignored directory nodes and give them their aggregated counts.
    for path, (files, size) in ignored_dirs.items():
        node = root
        for part in path.split("/"):
            node = node.children[part]
        node.ignored, node.files, node.size = True, files, size
        node.children.clear()
    _aggregate(root)

    largest = []
    for size, path in heapq.nsmallest(LARGEST_LIMIT, sizes, key=lambda t: (-t[0], t[1])):
        cls = classify(path)
        largest.append(FileStat(path=path, size=size, category=cls.category, language=cls.language))
    out_tree = _to_tree(root, node_budget)
    top_level = [c.model_copy(update={"children": None}) for c in out_tree.children or []]

    return StructureAnalysis(
        total_files=total_files,
        total_directories=directories,
        total_size_bytes=total_bytes,
        analyzed_files=analyzed_files,
        analyzed_size_bytes=analyzed_bytes,
        ignored_files=total_files - analyzed_files,
        ignored_size_bytes=total_bytes - analyzed_bytes,
        ignored_directories=sorted(
            (DirectoryStat(path=p, files=f, bytes=b) for p, (f, b) in ignored_dirs.items()),
            key=lambda d: (-d.files, d.path),
        )[:20],
        symlinks=symlinks,
        submodules=sorted(submodules)[:50],
        max_depth=max_depth,
        oversized_files=oversized,
        categories=sorted(
            (
                CategoryStat(category=c, files=n, bytes=category_bytes[c])
                for c, n in category_files.items()
            ),
            key=lambda c: (-c.files, c.category),
        ),
        largest_files=largest,
        largest_directories=sorted(
            (DirectoryStat(path=p, files=f, bytes=b) for p, (f, b) in dir_stats.items()),
            key=lambda d: (-d.bytes, d.path),
        )[:10],
        top_level=top_level,
        tree=out_tree,
        tree_node_budget=node_budget,
        truncated=tree.truncated,
        notes=list(tree.notes),
    )
