from app.analyzers.documentation_analyzer import (
    analyze_documentation,
    analyze_readme,
    python_docstring_coverage,
)
from app.services.repository_tree import RepositoryTree, TreeEntry

README = """# Demo Project

[![CI](https://github.com/o/r/actions/workflows/ci.yml/badge.svg)](https://github.com/o/r/actions)
[![PyPI](https://img.shields.io/pypi/v/demo)](https://pypi.org/project/demo)

## Table of Contents

## Features
Fast and **small**.

## Installation

```bash
pip install demo
# Not a heading inside a code block
```

## Usage
See [the guide](docs/guide.md), [API](./docs/api.md), [missing](docs/missing.md),
[root link](/LICENSE), [anchor](#usage), [external](https://example.com) and
[escape](../outside.md).

<img src="assets/logo.png" alt="logo">

License
-------
MIT
"""


def test_readme_metrics() -> None:
    paths = {"README.md", "docs/guide.md", "docs/api.md", "LICENSE", "assets/logo.png"}
    dirs = {"docs", "assets"}
    info = analyze_readme("README.md", README, paths, dirs)
    assert info.format == "markdown"
    assert info.headings == [
        "Demo Project",
        "Table of Contents",
        "Features",
        "Installation",
        "Usage",
        "License",
    ]
    sections = {s.key: s.present for s in info.sections}
    assert sections["install"] and sections["usage"] and sections["features"]
    assert sections["license"] and not sections["testing"] and not sections["deployment"]
    assert info.code_blocks == 1
    assert info.badges == 2 and info.images == 3
    assert info.has_table_of_contents
    assert info.broken_relative_links == ["docs/missing.md", "../outside.md"]
    assert info.words > 20


def test_rst_readme_headings() -> None:
    rst = "Title\n=====\n\nInstallation\n------------\n\n.. code-block:: bash\n\n   pip x\n"
    info = analyze_readme("README.rst", rst, {"README.rst"}, set())
    assert info.format == "rst"
    assert info.headings == ["Title", "Installation"]
    assert info.code_blocks == 1


def test_docstring_coverage() -> None:
    code = '''
"""module"""
def documented():
    """Yes."""
def undocumented():
    pass
def _private():
    pass
class Thing:
    """Doc."""
    def method(self):
        pass
'''
    cov = python_docstring_coverage({"src/m.py": code, "tests/test_m.py": "def test_x(): pass"})
    assert cov is not None
    assert (cov.public_definitions, cov.documented, cov.percent) == (4, 2, 50.0)
    assert cov.files_analyzed == 1
    assert python_docstring_coverage({"a.js": "x"}) is None


def test_analyze_documentation_end_to_end() -> None:
    files = {
        "README.md": "# Demo\n\n## Usage\nRun it.\n",
        "CONTRIBUTING.md": "x",
        "LICENSE": "MIT",
        ".github/SECURITY.md": "report here",
        ".github/ISSUE_TEMPLATE/bug.yml": "name: bug",
        ".github/pull_request_template.md": "## What",
        "docs/index.md": "# Docs",
        "docs/guide/setup.md": "# Setup",
        "mkdocs.yml": "site_name: demo",
        "examples/basic.py": "print(1)  # demo\n# comment\n",
        "src/app.py": "def run():\n    pass\n",
    }
    tree = RepositoryTree("sha", [TreeEntry(p, "file", len(t)) for p, t in files.items()])
    doc = analyze_documentation(tree, files, "MIT", "MIT License")

    assert doc.readme is not None and doc.readme.path == "README.md"
    present = {f.key: f.path for f in doc.files if f.present}
    assert present == {
        "contributing": "CONTRIBUTING.md",
        "license": "LICENSE",
        "security": ".github/SECURITY.md",
        "issue_templates": ".github/ISSUE_TEMPLATE/bug.yml",
        "pr_template": ".github/pull_request_template.md",
    }
    assert doc.license_spdx == "MIT" and doc.license_file == "LICENSE"
    assert doc.docs_directory is not None
    assert (doc.docs_directory.files, doc.docs_directory.doc_files) == (2, 2)
    assert doc.docs_directory.site_generator == "MkDocs"
    assert doc.examples_directory is not None and doc.examples_directory.files == 1
    assert doc.comment_density is not None and 0 < doc.comment_density < 1
    assert doc.python_docstrings is not None and doc.python_docstrings.percent == 0.0


def test_missing_readme_and_undownloaded_readme() -> None:
    tree = RepositoryTree("sha", [TreeEntry("src/a.py", "file", 3)])
    doc = analyze_documentation(tree, {}, None, None)
    assert doc.readme is None and not any(f.present for f in doc.files)
    assert doc.docs_directory is None

    tree = RepositoryTree("sha", [TreeEntry("README.md", "file", 10_000_000)])
    doc = analyze_documentation(tree, {}, None, None)
    assert doc.readme is None and "not downloaded" in doc.notes[0]
