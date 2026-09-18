# Changelog

All notable changes to RepoLens are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-19

First public release.

### Added

- Analysis of public GitHub repositories through the GitHub REST API, pinned to the default
  branch's head commit, with bounded downloads (per-file, total and file-count limits).
- **Structure:** interactive file tree, categories, largest files and directories, and
  generated/vendored directories that are counted but not analyzed.
- **Languages:** files, bytes and lines per language (exact for downloaded files, estimated for
  the rest), shown next to GitHub's own breakdown.
- **Dependencies:** static parsers for package.json, requirements files, pyproject.toml,
  Pipfile, setup.cfg, pom.xml, Gradle (Groovy/Kotlin), Cargo.toml, go.mod, composer.json and
  Gemfile, with scopes, version constraints, lockfile coverage and version conflicts.
- **Code quality:** McCabe complexity for Python via `ast` and a labelled heuristic for other
  languages, long files, TODO/FIXME/HACK/XXX markers, commented-out code, and tooling
  detection.
- **Documentation:** README sections and broken relative links, community files, docs site
  generators, comment density and Python docstring coverage.
- **Security indicators:** redacted secret patterns, committed sensitive files, risky code and
  configuration, GitHub Actions and Dockerfile checks, client-exposed env vars and `.gitignore`
  hygiene. All are presented as potential concerns, never as confirmed vulnerabilities.
- **Architecture:** modules, frameworks with evidence, entry points, infrastructure, and an
  interactive module graph built only from import statements that resolve to real files.
- **Health report:** seven transparent, point-based dimensions with per-check evidence.
- **Optional AI summary** (Anthropic or any OpenAI-compatible endpoint), built from the
  deterministic report only, with prompt-injection safeguards. Off by default.
- Export to Markdown, standalone HTML and JSON, plus print styles.
- Production hardening: per-client rate limits, concurrency and time limits, de-duplication
  of identical analyses, an egress allowlist, request IDs, security headers and a strict CSP.
- CI, Dockerfiles, docker-compose, a Render blueprint and deployment documentation.
