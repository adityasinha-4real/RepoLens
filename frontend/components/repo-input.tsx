"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { analyzePath, parseRepoInput } from "@/lib/repo-url";
import { cx } from "./ui/primitives";

export function RepoInput({
  initialValue = "",
  compact = false,
  autoFocus = false,
}: {
  initialValue?: string;
  compact?: boolean;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputId = useId();
  const errorId = `${inputId}-error`;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = parseRepoInput(value);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setSubmitting(true);
    router.push(analyzePath(result.owner, result.name));
  }

  return (
    <form onSubmit={submit} noValidate className="w-full" aria-label="Analyze a repository">
      <div className={cx("flex gap-2", compact ? "flex-row" : "flex-col sm:flex-row")}>
        <label htmlFor={inputId} className="sr-only">
          GitHub repository URL
        </label>
        <input
          id={inputId}
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          autoFocus={autoFocus}
          placeholder="https://github.com/owner/repository"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={cx(
            "min-w-0 flex-1 rounded-md border bg-surface px-3 font-mono text-sm outline-none transition-colors",
            "placeholder:text-muted/70 focus:border-accent focus:ring-2 focus:ring-accent/20",
            error ? "border-bad" : "border-border",
            compact ? "h-8" : "h-11",
          )}
        />
        <button
          type="submit"
          disabled={submitting}
          className={cx(
            "shrink-0 rounded-md bg-foreground px-4 text-sm font-medium text-background transition-opacity",
            "hover:opacity-90 disabled:opacity-60",
            compact ? "h-8" : "h-11",
          )}
        >
          {submitting ? "Opening…" : compact ? "Analyze" : "Analyze repository"}
        </button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="mt-2 text-sm text-bad">
          {error}
        </p>
      )}
    </form>
  );
}
