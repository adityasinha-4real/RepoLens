import type { AnalysisReport, ApiErrorBody, ProgressStage, StreamEvent } from "./api/types";

export class AnalysisError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(body: ApiErrorBody, status?: number) {
    super(body.message);
    this.name = "AnalysisError";
    this.code = body.code;
    this.status = status ?? body.status ?? 500;
    this.details = body.details ?? {};
  }
}

export interface StreamOptions {
  signal?: AbortSignal;
  onProgress?: (stage: ProgressStage, message: string) => void;
  fetchImpl?: typeof fetch;
}

async function errorFromResponse(response: Response): Promise<AnalysisError> {
  try {
    const body = (await response.json()) as { error?: ApiErrorBody };
    if (body?.error?.code) return new AnalysisError(body.error, response.status);
  } catch {
    // fall through to a generic error
  }
  return new AnalysisError(
    { code: "http_error", message: `The analysis service returned HTTP ${response.status}.` },
    response.status,
  );
}

/** Parse newline-delimited JSON from a byte stream, yielding one event per line. */
export async function* readNdjson(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) yield JSON.parse(line) as StreamEvent;
      }
    }
    const rest = (buffer + decoder.decode()).trim();
    if (rest) yield JSON.parse(rest) as StreamEvent;
  } finally {
    reader.releaseLock();
  }
}

/** Run an analysis through the streaming endpoint, reporting progress as it arrives. */
export async function streamAnalysis(
  repositoryUrl: string,
  { signal, onProgress, fetchImpl = fetch }: StreamOptions = {},
): Promise<AnalysisReport> {
  let response: Response;
  try {
    response = await fetchImpl("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repository_url: repositoryUrl }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new AnalysisError({
      code: "network_error",
      message: "Could not reach RepoLens. Check your connection and try again.",
    }, 0);
  }
  if (!response.ok || !response.body) throw await errorFromResponse(response);

  for await (const event of readNdjson(response.body)) {
    if (event.type === "progress") onProgress?.(event.stage, event.message);
    else if (event.type === "result") return event.report;
    else if (event.type === "error") throw new AnalysisError(event.error);
  }
  throw new AnalysisError({
    code: "incomplete_response",
    message: "The analysis ended before a result was received. Please try again.",
  });
}
