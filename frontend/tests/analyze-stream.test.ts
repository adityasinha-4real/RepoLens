import { describe, expect, it, vi } from "vitest";
import { AnalysisError, readNdjson, streamAnalysis } from "@/lib/analyze-stream";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

function fetchReturning(response: Response) {
  return vi.fn(async () => response) as unknown as typeof fetch;
}

describe("readNdjson", () => {
  it("handles events split across chunks and a trailing line without newline", async () => {
    const events = [];
    for await (const e of readNdjson(
      streamOf(['{"type":"progress","stage":"tr', 'ee","message":"x"}\n\n{"type":"pro', 'gress","stage":"analyze","message":"y"}']),
    )) {
      events.push(e);
    }
    expect(events).toEqual([
      { type: "progress", stage: "tree", message: "x" },
      { type: "progress", stage: "analyze", message: "y" },
    ]);
  });
});

describe("streamAnalysis", () => {
  it("reports progress and resolves with the report", async () => {
    const report = { repository: { full_name: "o/r" } };
    const body = streamOf([
      '{"type":"progress","stage":"metadata","message":"Fetching"}\n',
      `${JSON.stringify({ type: "result", report })}\n`,
    ]);
    const onProgress = vi.fn();
    const result = await streamAnalysis("o/r", {
      onProgress,
      fetchImpl: fetchReturning(new Response(body, { status: 200 })),
    });
    expect(onProgress).toHaveBeenCalledWith("metadata", "Fetching");
    expect(result).toEqual(report);
  });

  it("throws a typed error for error events", async () => {
    const body = streamOf([
      '{"type":"error","error":{"code":"repository_not_found","message":"Not found","details":{},"status":404}}\n',
    ]);
    const promise = streamAnalysis("o/r", { fetchImpl: fetchReturning(new Response(body)) });
    await expect(promise).rejects.toMatchObject({ code: "repository_not_found", status: 404 });
  });

  it("maps non-2xx JSON responses (e.g. rate limiting) to AnalysisError", async () => {
    const response = Response.json(
      { error: { code: "too_many_requests", message: "Slow down", details: { retry_after_seconds: 30 } } },
      { status: 429 },
    );
    const err = await streamAnalysis("o/r", { fetchImpl: fetchReturning(response) }).catch((e) => e);
    expect(err).toBeInstanceOf(AnalysisError);
    expect(err.status).toBe(429);
    expect(err.details.retry_after_seconds).toBe(30);
  });

  it("maps network failures and truncated streams", async () => {
    const failing = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(streamAnalysis("o/r", { fetchImpl: failing })).rejects.toMatchObject({
      code: "network_error",
    });
    const truncated = streamOf(['{"type":"progress","stage":"tree","message":"x"}\n']);
    await expect(
      streamAnalysis("o/r", { fetchImpl: fetchReturning(new Response(truncated)) }),
    ).rejects.toMatchObject({ code: "incomplete_response" });
  });
});
