"use client";

import { useEffect, useState } from "react";
import type { components } from "@/lib/api/schema.gen";
import { SparkIcon, SpinnerIcon } from "../ui/icons";
import { Badge, Note, Panel } from "../ui/primitives";

type AISummary = components["schemas"]["AISummary"];
type AIStatus = components["schemas"]["AIStatus"];

type State =
  | { status: "checking" }
  | { status: "disabled" }
  | { status: "ready"; ai: AIStatus }
  | { status: "loading"; ai: AIStatus }
  | { status: "done"; ai: AIStatus; summary: AISummary }
  | { status: "error"; ai: AIStatus; message: string };

export function AISummaryPanel({ repositoryUrl, fetchImpl = fetch }: { repositoryUrl: string; fetchImpl?: typeof fetch }) {
  const [state, setState] = useState<State>({ status: "checking" });

  useEffect(() => {
    let active = true;
    fetchImpl("/api/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { ai?: AIStatus } | null) => {
        if (!active) return;
        setState(body?.ai?.enabled ? { status: "ready", ai: body.ai } : { status: "disabled" });
      })
      .catch(() => active && setState({ status: "disabled" }));
    return () => {
      active = false;
    };
  }, [fetchImpl]);

  async function generate(ai: AIStatus) {
    setState({ status: "loading", ai });
    try {
      const response = await fetchImpl("/api/ai-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository_url: repositoryUrl }),
      });
      const body = await response.json();
      if (!response.ok) {
        setState({ status: "error", ai, message: body?.error?.message ?? "The AI summary could not be generated." });
        return;
      }
      setState({ status: "done", ai, summary: body as AISummary });
    } catch {
      setState({ status: "error", ai, message: "Could not reach RepoLens." });
    }
  }

  if (state.status === "checking") return null;
  if (state.status === "disabled") {
    return (
      <Panel id="ai" title="AI summary">
        <Note>
          AI summaries are not enabled on this RepoLens instance. Everything else in this report comes from
          deterministic static analysis and does not need AI. Operators can enable them by setting AI_PROVIDER.
        </Note>
      </Panel>
    );
  }

  return (
    <Panel
      id="ai"
      title={
        <span className="inline-flex items-center gap-2">
          AI summary <Badge tone="accent">optional · AI-generated</Badge>
        </span>
      }
      description={`${state.ai.provider} · ${state.ai.model}. Uses only the analysis shown on this page, never the raw repository.`}
      actions={
        state.status !== "done" ? (
          <button
            type="button"
            onClick={() => generate(state.ai)}
            disabled={state.status === "loading"}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-foreground px-3 text-sm font-medium text-background hover:opacity-90 disabled:opacity-60"
          >
            {state.status === "loading" ? <SpinnerIcon size={14} /> : <SparkIcon size={14} />}
            {state.status === "loading" ? "Generating…" : state.status === "error" ? "Try again" : "Generate summary"}
          </button>
        ) : null
      }
    >
      {state.status === "ready" && (
        <Note>Generate a plain-language orientation: purpose, architecture, key modules, entry points, concerns and onboarding steps.</Note>
      )}
      {state.status === "loading" && <Note>Asking the model. This usually takes 10 to 40 seconds.</Note>}
      {state.status === "error" && <p role="alert" className="text-sm text-bad">{state.message}</p>}
      {state.status === "done" && <SummaryBody summary={state.summary} />}
    </Panel>
  );
}

function SummaryBody({ summary }: { summary: AISummary }) {
  const list = (title: string, items: string[]) =>
    items.length > 0 && (
      <div>
        <h3 className="mb-1 text-xs font-medium text-muted">{title}</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    );
  return (
    <div className="space-y-4">
      <div role="note" className="rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-xs">
        {summary.disclaimer}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-medium text-muted">Purpose</h3>
        <p className="text-sm leading-relaxed">{summary.purpose}</p>
      </div>
      <div>
        <h3 className="mb-1 text-xs font-medium text-muted">Architecture</h3>
        <p className="text-sm leading-relaxed">{summary.architecture}</p>
      </div>
      {summary.key_modules.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted">Key modules</h3>
          <dl className="space-y-1.5 text-sm">
            {summary.key_modules.map((m) => (
              <div key={m.path}>
                <dt className="font-mono text-xs">{m.path}</dt>
                <dd className="text-muted">{m.description}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        {list("Likely entry points", summary.entry_points)}
        {list("Maintenance concerns", summary.maintenance_concerns)}
        {list("Onboarding suggestions", summary.onboarding_steps)}
      </div>
      <p className="text-[11px] text-muted">
        Generated for commit <span className="font-mono">{summary.commit_sha.slice(0, 7)}</span> by {summary.model}.
      </p>
    </div>
  );
}
