"""Count blank, comment and code lines using per-language comment syntax.

This is a lexical approximation, like cloc. Comment markers inside string literals are not
distinguished from real comments, and Python docstrings count as code.
"""

from dataclasses import dataclass

# fmt: off
# (line comment prefixes, block comment delimiters)
_C_STYLE = (("//",), (("/*", "*/"),))
_HASH = (("#",), ())
_SYNTAX: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {
    **{lang: _C_STYLE for lang in (
        "JavaScript", "TypeScript", "Java", "Kotlin", "Scala", "Groovy", "Go", "Rust", "C",
        "C++", "C#", "F#", "Objective-C", "Objective-C++", "Swift", "Dart", "PHP", "Solidity",
        "Zig", "V", "D", "Vue", "Svelte", "Astro", "Protocol Buffers", "Less", "SCSS", "Stylus",
    )},
    **{lang: _HASH for lang in (
        "Python", "Cython", "Ruby", "Perl", "Shell", "R", "Julia", "Elixir", "Crystal", "Nim",
        "Makefile", "Dockerfile", "CMake", "YAML", "TOML", "HCL", "Starlark", "Just",
        "PowerShell", "GraphQL",
    )},
    "CSS": ((), (("/*", "*/"),)),
    "Sass": (("//",), (("/*", "*/"),)),
    "HTML": ((), (("<!--", "-->"),)),
    "XML": ((), (("<!--", "-->"),)),
    "SQL": (("--",), (("/*", "*/"),)),
    "Lua": (("--",), (("--[[", "]]"),)),
    "Haskell": (("--",), (("{-", "-}"),)),
    "Elm": (("--",), (("{-", "-}"),)),
    "OCaml": ((), (("(*", "*)"),)),
    "Erlang": (("%",), ()),
    "TeX": (("%",), ()),
    "Clojure": ((";",), ()),
    "Assembly": ((";", "#"), ()),
    "Batchfile": (("REM ", "rem ", "::"), ()),
    "Visual Basic": (("'",), ()),
    "Nix": (("#",), (("/*", "*/"),)),
    "INI": ((";", "#"), ()),
}
# fmt: on


@dataclass
class LineCounts:
    total: int = 0
    code: int = 0
    comment: int = 0
    blank: int = 0

    def add(self, other: "LineCounts") -> None:
        self.total += other.total
        self.code += other.code
        self.comment += other.comment
        self.blank += other.blank


def count_lines(text: str, language: str | None) -> LineCounts:
    prefixes, blocks = _SYNTAX.get(language or "", ((), ()))
    counts = LineCounts()
    in_block: str | None = None  # expected end delimiter while inside a block comment
    for raw in text.splitlines():
        counts.total += 1
        line = raw.strip()
        if in_block is not None:
            counts.comment += 1
            if in_block in line:
                in_block = None
            continue
        if not line:
            counts.blank += 1
            continue
        block = next(((s, e) for s, e in blocks if line.startswith(s)), None)
        if block is not None:
            counts.comment += 1
            start, end = block
            if end not in line[len(start) :]:
                in_block = end
        elif prefixes and line.startswith(prefixes):
            counts.comment += 1
        else:
            counts.code += 1
    return counts
