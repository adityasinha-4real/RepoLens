import Link from "next/link";
import type { AnalysisError } from "@/lib/analyze-stream";
import { formatDateTime } from "@/lib/format";
import { AlertIcon } from "../ui/icons";

const COPY: Record<string, { title: string; hint?: string }> = {
  invalid_repository_url: { title: "That isn't a valid GitHub repository URL" },
  invalid_request: { title: "The request was invalid" },
  repository_not_found: {
    title: "Repository not found",
    hint: "Check the spelling. RepoLens can only analyze public repositories: private and deleted repositories look the same to it.",
  },
  repository_unavailable: {
    title: "Repository unavailable",
    hint: "GitHub refused access, the repository is empty, or it was taken down.",
  },
  rate_limited: {
    title: "GitHub API rate limit reached",
    hint: "GitHub limits how many requests this server can make. Try again after the reset time.",
  },
  too_many_requests: {
    title: "Too many analyses",
    hint: "This RepoLens instance limits analyses per client. Wait and try again.",
  },
  upstream_timeout: { title: "GitHub took too long to respond", hint: "Try again shortly." },
  upstream_error: { title: "GitHub returned an error", hint: "Try again shortly." },
  backend_unavailable: {
    title: "Analysis service unavailable",
    hint: "The RepoLens backend could not be reached. It may be starting up or down.",
  },
  network_error: { title: "Network error" },
  server_busy: {
    title: "RepoLens is busy",
    hint: "This instance limits how many analyses run at once. Try again in a minute.",
  },
  analysis_timeout: {
    title: "The analysis took too long",
    hint: "Very large repositories can exceed this instance's time limit.",
  },
  request_too_large: { title: "The request was too large" },
};

export function ErrorPanel({ error, onRetry }: { error: AnalysisError; onRetry?: () => void }) {
  const copy = COPY[error.code] ?? { title: "Analysis failed" };
  const resetAt = typeof error.details.reset_at === "string" ? error.details.reset_at : null;
  const retryAfter =
    typeof error.details.retry_after_seconds === "number" ? error.details.retry_after_seconds : null;
  const retryable = !["invalid_repository_url", "repository_not_found", "invalid_request"].includes(
    error.code,
  );

  return (
    <div
      role="alert"
      className="mx-auto mt-16 w-full max-w-md rounded-lg border border-bad/40 bg-surface p-6"
    >
      <div className="flex items-center gap-2 text-bad">
        <AlertIcon size={18} />
        <h1 className="text-base font-semibold">{copy.title}</h1>
      </div>
      <p className="mt-3 text-sm">{error.message}</p>
      {copy.hint && <p className="mt-2 text-sm text-muted">{copy.hint}</p>}
      {resetAt && (
        <p className="mt-2 text-sm text-muted">
          Limit resets at <span className="font-medium text-foreground">{formatDateTime(resetAt)}</span>.
        </p>
      )}
      {retryAfter !== null && (
        <p className="mt-2 text-sm text-muted">Retry after about {retryAfter} seconds.</p>
      )}
      <div className="mt-5 flex gap-2">
        {retryable && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="h-8 rounded-md bg-foreground px-3 text-sm font-medium text-background hover:opacity-90"
          >
            Try again
          </button>
        )}
        <Link
          href="/"
          className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm hover:bg-subtle"
        >
          Analyze another repository
        </Link>
      </div>
      <p className="mt-4 font-mono text-[11px] text-muted">code: {error.code}</p>
    </div>
  );
}
