import { backendUrl, jsonError } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const upstream = await fetch(backendUrl("/api/health"), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return Response.json(await upstream.json(), { status: upstream.status });
  } catch {
    return jsonError(503, "backend_unavailable", "The analysis service is unavailable.");
  }
}
