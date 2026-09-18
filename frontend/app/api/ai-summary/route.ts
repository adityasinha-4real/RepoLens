import { backendUrl, forwardedFor, jsonError } from "@/lib/server/backend";

export const maxDuration = 120;
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const raw = await request.text();
  if (raw.length > 2048) return jsonError(413, "invalid_request", "Request body is too large.");
  let repositoryUrl: unknown;
  try {
    repositoryUrl = (JSON.parse(raw) as { repository_url?: unknown }).repository_url;
  } catch {
    return jsonError(400, "invalid_request", "Request body must be JSON.");
  }
  if (typeof repositoryUrl !== "string" || !repositoryUrl.trim() || repositoryUrl.length > 512) {
    return jsonError(422, "invalid_repository_url", "Enter a GitHub repository URL.");
  }
  try {
    const upstream = await fetch(backendUrl("/api/ai/summary"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardedFor(request) },
      body: JSON.stringify({ repository_url: repositoryUrl }),
      signal: request.signal,
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return new Response(null, { status: 499 });
    return jsonError(503, "backend_unavailable", "The analysis service is unavailable. Try again later.");
  }
}
