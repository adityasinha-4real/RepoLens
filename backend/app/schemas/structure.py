from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TreeNode(BaseModel):
    name: str
    path: str
    type: Literal["dir", "file", "symlink", "submodule"]
    size: int = 0  # bytes; aggregated for directories
    files: int = 0  # number of files below a directory
    ignored: bool = False  # generated/vendored directory: counted, not analyzed
    children: list[TreeNode] | None = None
    omitted_children: int = 0  # children left out to keep the response bounded


class CategoryStat(BaseModel):
    category: str
    files: int
    bytes: int


class FileStat(BaseModel):
    path: str
    size: int
    category: str
    language: str | None = None


class DirectoryStat(BaseModel):
    path: str
    files: int
    bytes: int


class StructureAnalysis(BaseModel):
    total_files: int
    total_directories: int
    total_size_bytes: int
    analyzed_files: int
    analyzed_size_bytes: int
    ignored_files: int
    ignored_size_bytes: int
    ignored_directories: list[DirectoryStat]
    symlinks: int
    submodules: list[str]
    max_depth: int
    product_max_depth: int  # excluding tests, examples, fixtures and benchmarks
    oversized_files: int  # larger than the per-file download limit; not content-analyzed
    categories: list[CategoryStat]
    largest_files: list[FileStat]
    largest_directories: list[DirectoryStat]
    top_level: list[TreeNode]  # root children without grandchildren, for quick overview
    tree: TreeNode
    tree_node_budget: int
    truncated: bool
    notes: list[str]
