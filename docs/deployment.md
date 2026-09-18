# Deploying RepoLens

RepoLens has two deployable parts:

| Part | What it is | Recommended free host |
| --- | --- | --- |
| `frontend/` | Next.js UI plus small `/api/*` route handlers that proxy to the backend | Vercel (Hobby) |
| `backend/` | FastAPI analysis service (stateless, in-memory caches only) | Render (free web service); Fly.io, Railway and Koyeb also work |

No database is required. All configuration is environment variables. The full list with
comments is in [`.env.example`](../.env.example).

## 1. Backend on Render

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository. [`render.yaml`](../render.yaml)
   defines a free Docker web service named `repolens-api` that is built from `backend/Dockerfile`.
3. Set the environment variables Render asks for:

   | Variable | Value |
   | --- | --- |
   | `GITHUB_TOKEN` | Recommended. A fine-grained token with **no extra permissions** (public read-only access) raises GitHub's limit from 60 to 5,000 requests/hour. Each analysis uses 4 REST calls. |
   | `CORS_ORIGINS` | Your frontend origin, e.g. `https://repolens.vercel.app` |
   | `PROXY_SHARED_SECRET` | A long random string, e.g. `openssl rand -hex 32`. Use the same value for `REPOLENS_PROXY_SECRET` on Vercel. |
   | `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` | Optional; leave empty to disable AI summaries. |

4. Deploy, then check `https://<service>.onrender.com/api/health`, which should return `{"status":"ok",...}`.

> Render's free instances sleep when idle. The first request after a pause takes roughly 30–60 s
> while the service starts; the UI keeps showing progress during that time.

### Why the proxy secret matters

Rate limits are per client IP. On Render the API is publicly reachable, so it must not trust
`X-Forwarded-For` (anyone can send it). The frontend therefore reports the real client IP in
`X-RepoLens-Client-IP`, together with the shared secret. The backend trusts that header only
when the secret matches, using a constant-time comparison. Without the secret every visitor
reaches the backend from Vercel's addresses and shares one rate-limit bucket. That is safe,
but stricter than intended.

### Other hosts

The backend image honors `$PORT`, so it runs unchanged on Fly.io (`fly launch` from
`backend/`), Railway and Koyeb. For a VM, use `docker compose` (see below) or run
`uvicorn app.main:app --host 0.0.0.0 --port 8000` behind a reverse proxy with TLS.

## 2. Frontend on Vercel

1. **Add New → Project**, import the repository, and set **Root Directory** to `frontend`.
   The framework preset is detected as Next.js.
2. Environment variables:

   | Variable | Value |
   | --- | --- |
   | `REPOLENS_API_URL` | The backend URL, e.g. `https://repolens-api.onrender.com` (server-side only, never sent to browsers) |
   | `REPOLENS_PROXY_SECRET` | The same value as the backend's `PROXY_SHARED_SECRET` |

3. Deploy. The analysis route streams progress and declares `maxDuration = 120` s. If your
   Vercel plan caps function duration lower, set `ANALYSIS_TIMEOUT_SECONDS` on the backend below
   that cap so users get a clean timeout message instead of a dropped connection.

## 3. Everything on one machine (Docker Compose)

```bash
cp .env.example .env   # optional: add GITHUB_TOKEN and AI settings
docker compose up --build
# open http://localhost:3000
```

Only the web container publishes a port. The API is reachable exclusively through the
frontend on the internal network, so compose sets `TRUST_PROXY_HEADERS=true`.

## 4. Enabling AI summaries (optional)

Everything except the AI summary panel works without these settings.

| Provider | Settings |
| --- | --- |
| Claude (Anthropic) | `AI_PROVIDER=anthropic`, `AI_API_KEY=...`, optional `AI_MODEL` (default `claude-opus-5`). The Docker image already includes the SDK; for a pip install use `pip install -e ".[ai]"`. |
| OpenAI or any compatible API | `AI_PROVIDER=openai`, `AI_API_KEY=...`, `AI_MODEL=...`, and `AI_BASE_URL` for non-OpenAI endpoints (Groq, OpenRouter, ...) |
| Local model (free) | `AI_PROVIDER=openai`, `AI_BASE_URL=http://localhost:11434/v1`, `AI_MODEL=llama3.2` (Ollama) |

Summaries are cached per commit (`AI_CACHE_TTL_SECONDS`) and limited per client
(`AI_RATE_LIMIT_PER_HOUR`) to keep provider costs predictable.

## 5. Operating notes

- **Scaling:** caches, rate limits and in-flight de-duplication are per process. One instance is
  the intended free-tier setup. If you run several replicas, add rate limiting at the proxy
  or CDN.
- **Logs:** one access line per request (method, path, status, duration, client, request ID);
  send `X-Request-ID` to correlate. Tokens and keys are never logged.
- **Security headers:** both services send `nosniff`, `X-Frame-Options: DENY` and a referrer
  policy; the frontend adds a strict Content-Security-Policy.
- **Outbound traffic:** the backend only contacts `api.github.com`,
  `raw.githubusercontent.com` and, if configured, the AI endpoint. Every other host is refused.
