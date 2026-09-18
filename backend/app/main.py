"""RepoLens API entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="RepoLens API",
    version="0.1.0",
    description="Deterministic static analysis of public GitHub repositories.",
)
