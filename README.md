# RepoLens

> Understand any GitHub repository in minutes.

RepoLens analyzes a public GitHub repository and produces an engineering health report:
structure, languages, dependencies, code-quality indicators, documentation, static security
indicators and architecture. All of it comes from deterministic static analysis. An optional
AI provider can add a narrative summary; the tool works fully without one.

> **Status:** early development. See the roadmap below.

## Repository layout

```
backend/    FastAPI analysis service (Python)
frontend/   Next.js dashboard (TypeScript, Tailwind CSS)
```

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## License

[MIT](LICENSE)
