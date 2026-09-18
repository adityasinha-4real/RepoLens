from app.analyzers.language_analyzer import analyze_languages
from app.analyzers.line_counter import count_lines
from app.services.repository_tree import RepositoryTree, TreeEntry


def test_count_lines_python() -> None:
    text = "# comment\nimport os\n\n\ndef f():\n    return 1  # trailing\n"
    c = count_lines(text, "Python")
    assert (c.total, c.code, c.comment, c.blank) == (6, 3, 1, 2)


def test_count_lines_c_style_blocks() -> None:
    text = "/*\n * header\n */\nint x = 1;\n// note\n/* one-line */\nint y;\n"
    c = count_lines(text, "C")
    assert (c.total, c.code, c.comment, c.blank) == (7, 2, 5, 0)


def test_count_lines_lua_block_comment_takes_precedence() -> None:
    text = "--[[\nblock\n]]\nlocal x = 1\n-- line\n"
    c = count_lines(text, "Lua")
    assert (c.code, c.comment) == (1, 4)


def test_count_lines_unknown_language_counts_everything_as_code() -> None:
    c = count_lines("a\n\n# not a comment here\n", None)
    assert (c.total, c.code, c.blank, c.comment) == (3, 2, 1, 0)


def _tree(files: dict[str, int]) -> RepositoryTree:
    return RepositoryTree("sha", [TreeEntry(p, "file", s) for p, s in files.items()])


def test_language_stats_mix_counted_and_estimated_lines() -> None:
    py_text = "x = 1\n" * 10  # 60 bytes, 10 lines -> 6 bytes/line
    tree = _tree(
        {
            "a.py": len(py_text),
            "b.py": 120,  # not fetched -> estimated at 6 bytes/line = 20 lines
            "web/app.ts": 400,  # no TS sample -> falls back to global average (6 b/l) ~ 67 lines
            "README.md": 50,
            "package-lock.json": 99_999,  # lockfiles are excluded from language stats
            "node_modules/x/index.js": 5_000,  # ignored directory
            "logo.png": 1_000,
        }
    )
    result = analyze_languages(
        tree, {"a.py": py_text}, {"Python": 180, "TypeScript": 400}, "TypeScript"
    )
    by_lang = {s.language: s for s in result.languages}

    assert set(by_lang) == {"Python", "TypeScript", "Markdown"}
    py = by_lang["Python"]
    assert py.files == 2 and py.sampled_files == 1
    assert py.lines == 30 and py.lines_estimated
    assert py.code_lines == 10
    assert by_lang["TypeScript"].lines == round(400 / 6)
    assert by_lang["Markdown"].kind == "prose"
    assert result.counted_lines == 10
    assert result.total_lines == result.counted_lines + result.estimated_lines
    assert result.languages[0].language == "TypeScript"  # sorted by bytes
    assert abs(sum(s.percent_of_bytes for s in result.languages) - 100) < 0.1

    assert [g.language for g in result.github_breakdown] == ["TypeScript", "Python"]
    assert result.github_breakdown[0].percent == 68.97
    extensions = {e.extension for e in result.extensions}
    assert ".js" not in extensions  # from node_modules only
    assert ".png" in extensions


def test_language_stats_handle_empty_repository() -> None:
    result = analyze_languages(_tree({}), {}, {}, None)
    assert result.languages == [] and result.total_lines == 0
    assert result.github_breakdown == []
