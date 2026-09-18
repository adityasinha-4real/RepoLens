# RepoLens API. Small, non-root image; the app never executes analyzed repository code.
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
# The optional [ai] extra is included so AI summaries can be enabled with env vars alone.
RUN pip install ".[ai]" && useradd --create-home --uid 10001 repolens

USER repolens

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=4).status == 200 else 1)"

# PORT is provided by most PaaS hosts (Render, Railway, Fly, Koyeb); default 8000.
# No --proxy-headers: client addresses for rate limiting are resolved by the app itself
# (see PROXY_SHARED_SECRET / TRUST_PROXY_HEADERS), never from spoofable headers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
