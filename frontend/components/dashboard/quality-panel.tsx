"use client";

import { useState } from "react";
import type { AnalysisReport } from "@/lib/api/types";
import { formatBytes, formatInteger } from "@/lib/format";
import { CheckIcon, XIcon } from "../ui/icons";
import { Badge, Empty, Note, Panel, Stat, cx } from "../ui/primitives";

const TAGS = ["TODO", "FIXME", "HACK", "XXX"] as const;

export function blobUrl(report: AnalysisReport, path: string, line?: number | null): string {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return `${report.repository.html_url}/blob/${report.analysis.commit_sha}/${encoded}${line ? `#L${line}` : ""}`;
}

export function QualityPanel({ report }: { report: AnalysisReport }) {
  const q = report.quality;
  const [tag, setTag] = useState<string>("all");
  const markers = q.markers.filter((m) => tag === "all" || m.tag === tag);
  const totalMarkers = Object.values(q.marker_counts).reduce((a, b) => a + b, 0);
  const tooling: [string, string[]][] = [
    ["CI", q.tooling.ci],
    ["Linters", q.tooling.linters],
    ["Formatters", q.tooling.formatters],
    ["Type checking", q.tooling.type_checkers],
    ["Test frameworks", q.tooling.test_frameworks],
  ];

  return (
    <Panel id="quality" title="Code quality" description={q.coverage_note}>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Source files" value={formatInteger(q.source_files)} />
        <Stat label="Test files" value={formatInteger(q.test_files)}
          hint={q.test_to_source_ratio !== null && q.test_to_source_ratio !== undefined ? `ratio ${q.test_to_source_ratio.toFixed(2)}` : undefined} />
        <Stat label="Avg. file size" value={formatBytes(q.average_source_file_bytes)} />
        <Stat label="Avg. lines / file" value={q.average_lines_per_sampled_file ?? "—"} hint="downloaded files" />
        <Stat label={`Files > ${q.long_file_threshold} lines`} value={formatInteger(q.long_file_count)} />
        <Stat label="Complexity hotspots" value={formatInteger(q.high_complexity_count)} />
      </dl>

      <div className="mt-5 grid gap-x-6 gap-y-2 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-3">
        {tooling.map(([label, items]) => (
          <div key={label} className="flex items-start gap-2 text-sm">
            {items.length ? <CheckIcon size={14} className="mt-0.5 shrink-0 text-good" /> : <XIcon size={14} className="mt-0.5 shrink-0 text-muted" />}
            <span>
              <span className={items.length ? "" : "text-muted"}>{label}</span>
              {items.length > 0 && <span className="ml-1.5 text-xs text-muted">{items.join(", ")}</span>}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-sm">
          {q.tooling.pre_commit ? <CheckIcon size={14} className="text-good" /> : <XIcon size={14} className="text-muted" />}
          <span className={q.tooling.pre_commit ? "" : "text-muted"}>Pre-commit hooks</span>
          {q.tooling.editorconfig && <Badge>EditorConfig</Badge>}
        </div>
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-2 text-xs font-medium text-muted">
            Complexity hotspots <span className="font-normal">(McCabe &gt; {q.complexity_threshold} for Python; heuristic elsewhere)</span>
          </h3>
          {q.complexity_hotspots.length ? (
            <table className="w-full table-fixed text-sm">
              <tbody>
                {q.complexity_hotspots.slice(0, 12).map((c) => (
                  <tr key={`${c.path}:${c.name}:${c.line}`} className="border-b border-border/60 last:border-0">
                    <td className="max-w-0 py-1 pr-2">
                      <a href={blobUrl(report, c.path, c.line)} target="_blank" rel="noopener noreferrer"
                        className="block truncate font-mono text-xs hover:text-accent" title={c.path}>
                        {c.name ? `${c.name}` : c.path}
                      </a>
                      {c.name && <span className="block truncate text-[11px] text-muted">{c.path}:{c.line}</span>}
                    </td>
                    <td className="w-36 whitespace-nowrap py-1 text-right text-xs tabular-nums">
                      {c.method === "python-ast" ? `CC ${c.complexity}` : `${c.complexity} branches · depth ${c.max_nesting}`}
                    </td>
                    <td className="w-20 py-1 pl-2 text-right">
                      <Badge tone={c.method === "python-ast" ? "info" : "neutral"}>{c.method === "python-ast" ? "AST" : "heuristic"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>No hotspots above the thresholds in the downloaded files.</Empty>
          )}
          <h3 className="mb-2 mt-5 text-xs font-medium text-muted">Longest files</h3>
          {q.long_files.length ? (
            <ul className="space-y-1 text-sm">
              {q.long_files.slice(0, 8).map((f) => (
                <li key={f.path} className="flex justify-between gap-2">
                  <a href={blobUrl(report, f.path)} target="_blank" rel="noopener noreferrer"
                    className="truncate font-mono text-xs hover:text-accent" title={f.path}>{f.path}</a>
                  <span className="shrink-0 text-xs tabular-nums text-muted">
                    {f.estimated ? "≈" : ""}{formatInteger(f.lines)} lines
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No source files exceed {q.long_file_threshold} lines.</p>
          )}
        </div>

        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-medium text-muted">Markers in comments ({formatInteger(totalMarkers)})</h3>
            <div role="group" aria-label="Filter markers" className="flex gap-1 text-xs">
              {(["all", ...TAGS] as const).map((t) => (
                <button key={t} type="button" aria-pressed={tag === t} onClick={() => setTag(t)}
                  className={cx("rounded border px-1.5 py-0.5", tag === t ? "border-accent text-accent" : "border-border text-muted")}>
                  {t === "all" ? "All" : `${t} ${q.marker_counts[t] ?? 0}`}
                </button>
              ))}
            </div>
          </div>
          {markers.length ? (
            <ul className="max-h-72 space-y-1.5 overflow-auto text-sm">
              {markers.slice(0, 100).map((m) => (
                <li key={`${m.path}:${m.line}`} className="min-w-0">
                  <a href={blobUrl(report, m.path, m.line)} target="_blank" rel="noopener noreferrer"
                    className="block truncate font-mono text-[11px] text-muted hover:text-accent">
                    {m.path}:{m.line}
                  </a>
                  <span className="block truncate text-xs">{m.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No markers found in the downloaded files.</Empty>
          )}
          {q.markers_truncated && <Note>Only the first {q.markers.length} markers are listed.</Note>}

          <h3 className="mb-2 mt-5 text-xs font-medium text-muted">
            Possible commented-out code ({formatInteger(q.commented_code_lines)} lines, heuristic)
          </h3>
          {q.commented_code_files.length ? (
            <ul className="space-y-1 text-sm">
              {q.commented_code_files.slice(0, 6).map((f) => (
                <li key={f.path} className="flex justify-between gap-2">
                  <span className="truncate font-mono text-xs" title={f.path}>{f.path}</span>
                  <span className="shrink-0 text-xs tabular-nums text-muted">{f.lines} lines</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">None detected.</p>
          )}
        </div>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-muted">Methodology</summary>
        <div className="mt-2"><Note>{q.methodology}</Note></div>
      </details>
    </Panel>
  );
}
