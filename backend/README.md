# RepoLens backend

FastAPI service that performs static, read-only analysis of public GitHub repositories.
See the [project README](../README.md) for setup, configuration and architecture.

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip
uvicorn app.main:app --reload --port 8000
pytest
ruff check . && ruff format --check .
```
