"""Repository tree model and sanitization of the untrusted tree returned by GitHub."""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

EntryType = Literal["file", "dir", "symlink", "submodule"]
MAX_PATH_LENGTH = 1024


@dataclass(frozen=True)
class TreeEntry:
    path: str
    type: EntryType
    size: int = 0  # bytes; 0 for non-files


@dataclass
class RepositoryTree:
    commit_sha: str
    entries: list[TreeEntry]
    truncated_by_github: bool = False
    truncated_by_limit: bool = False
    unsafe_paths_skipped: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return self.truncated_by_github or self.truncated_by_limit

    def files(self) -> list[TreeEntry]:
        return [e for e in self.entries if e.type == "file"]


def is_safe_path(path: object) -> bool:
    """Reject paths that could escape a directory or confuse downstream consumers."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH:
        return False
    if path.startswith("/") or "\\" in path:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return False
    return all(seg not in ("", ".", "..") for seg in path.split("/"))


def _entry_type(raw_type: str, mode: str) -> EntryType | None:
    if raw_type == "tree":
        return "dir"
    if raw_type == "commit":
        return "submodule"
    if raw_type == "blob":
        return "symlink" if mode == "120000" else "file"
    return None


def build_tree(
    commit_sha: str, raw_entries: Any, *, github_truncated: bool, max_entries: int
) -> RepositoryTree:
    """Validate raw git-tree entries from the GitHub API into a RepositoryTree."""
    tree = RepositoryTree(
        commit_sha=commit_sha, entries=[], truncated_by_github=bool(github_truncated)
    )
    if not isinstance(raw_entries, list):
        return tree
    for raw in raw_entries:
        if len(tree.entries) >= max_entries:
            tree.truncated_by_limit = True
            break
        if not isinstance(raw, dict):
            continue
        path = raw.get("path")
        entry_type = _entry_type(str(raw.get("type")), str(raw.get("mode")))
        if entry_type is None:
            continue
        if not is_safe_path(path):
            tree.unsafe_paths_skipped += 1
            continue
        size = raw.get("size") if entry_type == "file" else 0
        if not isinstance(size, int) or size < 0:
            size = 0
        tree.entries.append(TreeEntry(path=path, type=entry_type, size=size))

    if tree.truncated_by_github:
        tree.notes.append(
            "GitHub truncated the file tree because the repository is very large; "
            "results cover a partial tree."
        )
    if tree.truncated_by_limit:
        tree.notes.append(f"Only the first {max_entries:,} tree entries were analyzed.")
    if tree.unsafe_paths_skipped:
        logger.warning("Skipped %d unsafe tree paths", tree.unsafe_paths_skipped)
        tree.notes.append(f"{tree.unsafe_paths_skipped} entries with unsafe paths were skipped.")
    return tree
