"use client";

import { useEffect, useState } from "react";
import type { ProgressStage } from "@/lib/api/types";
import { CheckIcon, SpinnerIcon } from "../ui/icons";
import { cx } from "../ui/primitives";

export const STAGES: { key: ProgressStage; label: string }[] = [
  { key: "validate", label: "Validate repository URL" },
  { key: "metadata", label: "Fetch repository metadata" },
  { key: "tree", label: "Fetch file tree" },
  { key: "contents", label: "Download relevant files" },
  { key: "analyze", label: "Run static analysis" },
];

export function ProgressPanel({
  repo,
  stage,
  message,
}: {
  repo: string;
  stage: ProgressStage | null;
  message: string | null;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  const activeIndex = stage ? STAGES.findIndex((s) => s.key === stage) : -1;

  return (
    <div
      className="mx-auto mt-16 w-full max-w-md rounded-lg border border-border bg-surface p-6"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="text-sm text-muted">Analyzing</p>
      <p className="mt-0.5 truncate font-mono text-base font-medium">{repo}</p>
      <ol className="mt-5 space-y-2.5">
        {STAGES.map((s, i) => {
          const done = i < activeIndex;
          const active = i === activeIndex || (activeIndex === -1 && i === 0);
          return (
            <li key={s.key} className="flex items-center gap-2.5 text-sm">
              <span
                className={cx(
                  "grid size-5 shrink-0 place-items-center rounded-full border",
                  done && "border-good bg-good/10 text-good",
                  active && "border-accent text-accent",
                  !done && !active && "border-border text-muted",
                )}
              >
                {done ? <CheckIcon size={12} /> : active ? <SpinnerIcon size={12} /> : null}
              </span>
              <span className={cx(!done && !active && "text-muted", active && "font-medium")}>
                {s.label}
              </span>
              <span className="sr-only">{done ? "(done)" : active ? "(in progress)" : ""}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-5 min-h-4 text-xs text-muted">
        {message ?? "Starting…"} · {elapsed}s
      </p>
      <p className="mt-1 text-xs text-muted">
        Large repositories can take up to a minute. Nothing is cloned or executed.
      </p>
    </div>
  );
}
