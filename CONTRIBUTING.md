# Contributing to RepoLens

Thanks for your interest in improving RepoLens. This guide covers what you need to get a change merged.

## Ground rules

1. **Never execute repository code.** RepoLens is a static analyzer. A change must not run,
   install, build or import anything from an analyzed repository (`npm install`, `pip install`,
   `make`, `eval`, and so on). Pull requests that do will be rejected.
2. **Deterministic first.** New insights should come from measurable, reproducible analysis.
   The AI summary is an optional layer on top and must never be required.
3. **No fabricated data.** Never invent statistics or relationships, and never show placeholder
   numbers as if they were real results. If something cannot be determined, say so.
4. **Careful wording for security findings.** They are *indicators*, not confirmed vulnerabilities.
   Never state that a repository "is secure".
5. **Keep dependencies lean.** Justify any new runtime dependency in the PR description.

## Development setup

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv
.venv/bin/pip install -e ".[dev]"       # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .

# Frontend (Node 20+)
cd frontend
npm ci
npm run lint && npm run typecheck && npm test && npm run build
```

Copy `.env.example` to `backend/.env` and `frontend/.env.local` as needed. A `GITHUB_TOKEN`
is optional, but without one GitHub allows only 60 API requests per hour.

## Workflow

1. Fork the repo and create a branch: `feat/short-description` or `fix/short-description`.
2. Add or update tests for the behavior you change. Tests should exercise real logic
   (parsers, analyzers, error handling), not just check that mocks exist.
3. Make sure all the checks above pass locally. CI runs the same commands.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`).
5. Open a pull request describing what changed, why, and how you tested it.

## Adding an analyzer

Analyzers live in `backend/app/analyzers/`. Each one is a pure function that takes the
already-fetched repository snapshot and returns a Pydantic model defined in
`backend/app/schemas/`. Analyzers must not perform network I/O. Fetching is the job of
`app/services/`. That keeps analyzers fast and easy to test with fixtures.

## Reporting security issues

Please do not open public issues for vulnerabilities in RepoLens itself. See [SECURITY.md](SECURITY.md).
