import "server-only";

/** Base URL of the FastAPI backend. Server-side only: never exposed to the browser. */
export function backendUrl(path: string): string {
  const base = (process.env.REPOLENS_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
  return `${base}${path}`;
}

export function jsonError(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message, details: {} } }, { status });
}

/**
 * Tell the backend who the real client is, so per-client rate limits work behind this proxy.
 * The client IP is only trusted by the backend when REPOLENS_PROXY_SECRET matches its
 * PROXY_SHARED_SECRET (or, on private networks, when it sets TRUST_PROXY_HEADERS).
 */
export function forwardedFor(request: Request): Record<string, string> {
  const raw = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  const ip = raw?.split(",")[0].trim();
  const headers: Record<string, string> = {};
  if (ip) {
    headers["X-Forwarded-For"] = ip;
    headers["X-RepoLens-Client-IP"] = ip;
  }
  const secret = process.env.REPOLENS_PROXY_SECRET;
  if (secret) headers["X-RepoLens-Proxy-Secret"] = secret;
  return headers;
}
