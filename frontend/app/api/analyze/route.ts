import { backendUrl, forwardedFor, jsonError } from "@/lib/server/backend";

// Analyses of large repositories can take a while; the response streams progress meanwhile.
export const maxDuration = 120;
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 2048;

export async function POST(request: Request): Promise<Response> {
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return jsonError(413, "invalid_request", "Request body is too large.");
  }
  let repositoryUrl: unknown;
  try {
    repositoryUrl = (JSON.parse(raw) as { repository_url?: unknown }).repository_url;
  } catch {
    return jsonError(400, "invalid_request", "Request body must be JSON.");
  }
  if (typeof repositoryUrl !== "string" || !repositoryUrl.trim() || repositoryUrl.length > 512) {
    return jsonError(422, "invalid_repository_url", "Enter a GitHub repository URL.");
  }

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl("/api/analyze/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardedFor(request) },
      body: JSON.stringify({ repository_url: repositoryUrl }),
      signal: request.signal, // cancel the backend work if the browser goes away
      cache: "no-store",
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return new Response(null, { status: 499 });
    return jsonError(503, "backend_unavailable", "The analysis service is unavailable. Try again later.");
  }

  if (!upstream.ok || !upstream.body) {
    const body = await upstream.text();
    return new Response(body || null, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        ...(upstream.headers.get("retry-after")
          ? { "Retry-After": upstream.headers.get("retry-after") as string }
          : {}),
      },
    });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    },
  });
}
