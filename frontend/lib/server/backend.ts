import "server-only";

/** Base URL of the FastAPI backend. Server-side only: never exposed to the browser. */
export function backendUrl(path: string): string {
  const base = (process.env.REPOLENS_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
  return `${base}${path}`;
}

export function jsonError(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message, details: {} } }, { status });
}

/** Forward the caller's IP so the backend can apply per-client rate limits. */
export function forwardedFor(request: Request): Record<string, string> {
  const forwarded = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  return forwarded ? { "X-Forwarded-For": forwarded.split(",")[0].trim() } : {};
}
