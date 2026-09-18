"""Language statistics from the file tree, with exact line counts where content was fetched."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.analyzers.file_classifier import FileCategory, classify, ignored_segment
from app.analyzers.line_counter import LineCounts, count_lines
from app.schemas.languages import (
    ExtensionStat,
    GitHubLanguageShare,
    LanguageAnalysis,
    LanguageKind,
    LanguageStat,
)
from app.services.repository_tree import RepositoryTree

_EXCLUDED = {FileCategory.LOCKFILE, FileCategory.GENERATED, FileCategory.BINARY, FileCategory.ASSET}
_PROSE = {"Markdown", "MDX", "reStructuredText", "AsciiDoc", "TeX"}
_MARKUP = {"HTML", "CSS", "SCSS", "Sass", "Less", "Stylus", "XML"}
_DATA = {"JSON", "YAML", "TOML", "INI", "CSV"}
DEFAULT_BYTES_PER_LINE = 40.0

METHODOLOGY = (
    "Languages are detected from file extensions and well-known filenames, excluding "
    "ignored directories, lockfiles, generated files and binaries. Line counts are exact for "
    "downloaded files. For the remaining files they are estimated from file size using the "
    "average bytes-per-line measured for the same language. The GitHub breakdown comes "
    "straight from GitHub's linguist-based API and can differ from RepoLens's counts."
)


def language_kind(language: str) -> LanguageKind:
    if language in _PROSE:
        return "prose"
    if language in _MARKUP:
        return "markup"
    if language in _DATA:
        return "data"
    return "programming"


@dataclass
class _Acc:
    files: int = 0
    bytes: int = 0
    sampled: int = 0
    sampled_bytes: int = 0
    unsampled_bytes: int = 0
    counts: LineCounts = field(default_factory=LineCounts)


def analyze_languages(
    tree: RepositoryTree,
    contents: dict[str, str],
    github_languages: dict[str, int],
    primary_language: str | None,
) -> LanguageAnalysis:
    acc: dict[str, _Acc] = defaultdict(_Acc)
    extensions: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for entry in tree.files():
        if ignored_segment(entry.path) is not None:
            continue
        ext = PurePosixPath(entry.path).suffix.lower() or "(none)"
        extensions[ext][0] += 1
        extensions[ext][1] += entry.size
        cls = classify(entry.path)
        if cls.language is None or cls.category in _EXCLUDED:
            continue
        a = acc[cls.language]
        a.files += 1
        a.bytes += entry.size
        text = contents.get(entry.path)
        if text is None:
            a.unsampled_bytes += entry.size
        else:
            a.sampled += 1
            a.sampled_bytes += entry.size
            a.counts.add(count_lines(text, cls.language))

    total_sampled_bytes = sum(a.sampled_bytes for a in acc.values())
    total_sampled_lines = sum(a.counts.total for a in acc.values())
    global_bpl = (
        total_sampled_bytes / total_sampled_lines if total_sampled_lines else DEFAULT_BYTES_PER_LINE
    )
    language_bytes = sum(a.bytes for a in acc.values()) or 1

    stats: list[LanguageStat] = []
    counted = estimated = sampled_files = 0
    for language, a in acc.items():
        bpl = a.sampled_bytes / a.counts.total if a.counts.total else global_bpl
        est = round(a.unsampled_bytes / bpl) if a.unsampled_bytes and bpl > 0 else 0
        counted += a.counts.total
        estimated += est
        sampled_files += a.sampled
        stats.append(
            LanguageStat(
                language=language,
                kind=language_kind(language),
                files=a.files,
                bytes=a.bytes,
                percent_of_bytes=round(100 * a.bytes / language_bytes, 2),
                lines=a.counts.total + est,
                lines_estimated=est > 0,
                sampled_files=a.sampled,
                code_lines=a.counts.code,
                comment_lines=a.counts.comment,
                blank_lines=a.counts.blank,
            )
        )
    stats.sort(key=lambda s: (-s.bytes, s.language))

    gh_total = sum(v for v in github_languages.values() if isinstance(v, int)) or 1
    github_breakdown = sorted(
        (
            GitHubLanguageShare(language=k, bytes=v, percent=round(100 * v / gh_total, 2))
            for k, v in github_languages.items()
            if isinstance(v, int) and v >= 0
        ),
        key=lambda s: (-s.bytes, s.language),
    )

    return LanguageAnalysis(
        primary_language=primary_language,
        github_breakdown=github_breakdown,
        languages=stats,
        extensions=sorted(
            (ExtensionStat(extension=k, files=f, bytes=b) for k, (f, b) in extensions.items()),
            key=lambda e: (-e.files, e.extension),
        )[:25],
        total_lines=counted + estimated,
        counted_lines=counted,
        estimated_lines=estimated,
        sampled_files=sampled_files,
        methodology=METHODOLOGY,
    )
