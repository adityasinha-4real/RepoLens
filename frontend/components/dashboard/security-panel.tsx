"use client";

import { useMemo, useState } from "react";
import type { AnalysisReport, SecurityFinding } from "@/lib/api/types";
import { formatInteger } from "@/lib/format";
import { AlertIcon, CheckIcon, XIcon } from "../ui/icons";
import { Badge, Empty, Note, Panel, cx } from "../ui/primitives";
import { blobUrl } from "./quality-panel";

const SEVERITIES = ["high", "medium", "low", "info"] as const;
const SEVERITY_TONE = { high: "bad", medium: "warn", low: "info", info: "neutral" } as const;

export function SecurityPanel({ report }: { report: AnalysisReport }) {
  const sec = report.security;
  const [severity, setSeverity] = useState<string>("all");
  const [includeTests, setIncludeTests] = useState(false);
  const visible = useMemo(
    () => sec.findings.filter((f) => (includeTests || !f.in_test) && (severity === "all" || f.severity === severity)),
    [sec.findings, includeTests, severity],
  );
  const testCount = sec.findings.filter((f) => f.in_test).length;

  return (
    <Panel id="security" title="Security indicators" description={sec.coverage_note}>
      <div className="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/5 p-3 text-sm" role="note">
        <AlertIcon size={16} className="mt-0.5 shrink-0 text-warn" />
        <p>{sec.disclaimer}</p>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filter by severity" className="flex flex-wrap gap-1 text-xs">
          <FilterButton active={severity === "all"} onClick={() => setSeverity("all")}>
            All {formatInteger(sec.findings.length)}
          </FilterButton>
          {SEVERITIES.map((s) => (
            <FilterButton key={s} active={severity === s} onClick={() => setSeverity(s)}>
              <span className="capitalize">{s}</span> {sec.counts_by_severity[s] ?? 0}
            </FilterButton>
          ))}
        </div>
        {testCount > 0 && (
          <label className="ml-auto flex items-center gap-1.5 text-xs text-muted">
            <input type="checkbox" checked={includeTests} onChange={(e) => setIncludeTests(e.target.checked)} />
            Include {testCount} finding(s) in tests, examples and fixtures
          </label>
        )}
      </div>

      <div className="mt-3">
        {visible.length ? (
          <ul aria-label="Findings" className="divide-y divide-border rounded-md border border-border">
            {visible.slice(0, 150).map((f, i) => (
              <FindingRow key={`${f.rule}:${f.path}:${f.line}:${i}`} report={report} finding={f} />
            ))}
          </ul>
        ) : (
          <Empty>
            {sec.findings.length === 0
              ? "No potential concerns were detected by these rules. That does not mean the repository is secure."
              : "No findings match the current filters."}
          </Empty>
        )}
        {sec.findings_truncated && <Note>The report lists the first {sec.findings.length} findings.</Note>}
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">Security hygiene</h3>
          <ul className="space-y-1.5">
            {sec.hygiene.map((h) => (
              <li key={h.key} className="flex items-start gap-2 text-sm">
                {h.passed ? <CheckIcon size={14} className="mt-0.5 shrink-0 text-good" aria-label="passed" /> : <XIcon size={14} className="mt-0.5 shrink-0 text-bad" aria-label="not passed" />}
                <span className="min-w-0">
                  {h.label}
                  <span className="block truncate text-xs text-muted" title={h.detail}>{h.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">
            Environment variables read by the code ({formatInteger(sec.env_variables.length)} in {formatInteger(sec.env_variable_files)} files)
          </h3>
          {sec.env_variables.length ? (
            <div className="flex max-h-40 flex-wrap gap-1 overflow-auto">
              {sec.env_variables.map((v) => (
                <span key={v} className="rounded bg-subtle px-1.5 py-0.5 font-mono text-[11px]">{v}</span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted">None detected in the downloaded files.</p>
          )}
        </div>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-muted">Rules evaluated ({sec.rules.length})</summary>
        <ul className="mt-2 grid gap-1.5 md:grid-cols-2">
          {sec.rules.map((r) => (
            <li key={r.id} className="text-xs">
              <Badge tone={SEVERITY_TONE[r.severity]}>{r.severity}</Badge>{" "}
              <span className="font-medium">{r.title}</span>
              <span className="block text-muted">{r.description}</span>
            </li>
          ))}
        </ul>
      </details>
    </Panel>
  );
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
      className={cx("rounded border px-2 py-0.5", active ? "border-accent text-accent" : "border-border text-muted hover:text-foreground")}>
      {children}
    </button>
  );
}

function FindingRow({ report, finding: f }: { report: AnalysisReport; finding: SecurityFinding }) {
  const linkable = !f.path.startsWith("(");
  return (
    <li className="px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY_TONE[f.severity]}>{f.severity}</Badge>
        <span className="text-sm font-medium">{f.title}</span>
        {f.in_test && <Badge>test/example</Badge>}
        <span className="text-[11px] text-muted">confidence: {f.confidence}</span>
      </div>
      <div className="mt-1 min-w-0">
        {linkable ? (
          <a href={blobUrl(report, f.path, f.line)} target="_blank" rel="noopener noreferrer"
            className="font-mono text-xs text-muted hover:text-accent">
            {f.path}{f.line ? `:${f.line}` : ""}
          </a>
        ) : (
          <span className="font-mono text-xs text-muted">{f.path}</span>
        )}
      </div>
      {f.evidence && (
        <pre className="mt-1.5 overflow-x-auto rounded bg-subtle px-2 py-1 font-mono text-[11px]"><code>{f.evidence}</code></pre>
      )}
      <p className="mt-1 text-xs text-muted">{f.description}</p>
    </li>
  );
}
