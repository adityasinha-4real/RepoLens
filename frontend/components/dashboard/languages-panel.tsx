"use client";

import { useMemo, useState } from "react";
import type { LanguageAnalysis } from "@/lib/api/types";
import { languageColor } from "@/lib/colors";
import { formatBytes, formatCount, formatInteger } from "@/lib/format";
import { StackedBar } from "../charts/charts";
import { Badge, Empty, Note, Panel, cx } from "../ui/primitives";

type Kind = "programming" | "all";

export function LanguagesPanel({ languages }: { languages: LanguageAnalysis }) {
  const [kind, setKind] = useState<Kind>("programming");
  const rows = useMemo(
    () => languages.languages.filter((l) => kind === "all" || l.kind === "programming"),
    [languages.languages, kind],
  );
  const totalBytes = rows.reduce((sum, l) => sum + l.bytes, 0) || 1;

  return (
    <Panel
      id="languages"
      title="Languages"
      description={`${formatInteger(languages.total_lines)} lines, of which ${formatInteger(languages.counted_lines)} were counted in ${formatInteger(languages.sampled_files)} downloaded files and the rest estimated from file size.`}
      actions={
        <div role="group" aria-label="Language kinds" className="flex rounded-md border border-border p-0.5 text-xs">
          {(["programming", "all"] as const).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={cx("rounded px-2 py-0.5", kind === k ? "bg-subtle font-medium" : "text-muted")}
            >
              {k === "programming" ? "Code" : "All"}
            </button>
          ))}
        </div>
      }
    >
      {rows.length === 0 ? (
        <Empty>No {kind === "programming" ? "programming " : ""}languages detected.</Empty>
      ) : (
        <>
          <StackedBar
            label="Language share by bytes"
            format={formatBytes}
            segments={rows.map((l) => ({
              key: l.language,
              label: l.language,
              value: l.bytes,
              color: languageColor(l.language),
            }))}
          />
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="py-1.5 font-medium">Language</th>
                  <th className="py-1.5 text-right font-medium">Files</th>
                  <th className="py-1.5 text-right font-medium">Lines</th>
                  <th className="py-1.5 text-right font-medium">Size</th>
                  <th className="py-1.5 text-right font-medium">Share</th>
                  <th className="py-1.5 text-right font-medium" title="Comment lines / (code + comment) in downloaded files">
                    Comments
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 15).map((l) => {
                  const commented = l.code_lines + l.comment_lines;
                  return (
                    <tr key={l.language} className="border-b border-border/60 last:border-0">
                      <td className="py-1.5">
                        <span className="inline-flex items-center gap-2">
                          <span className="size-2 rounded-full" style={{ background: languageColor(l.language) }} />
                          {l.language}
                          {l.kind !== "programming" && <Badge>{l.kind}</Badge>}
                        </span>
                      </td>
                      <td className="py-1.5 text-right tabular-nums">{formatInteger(l.files)}</td>
                      <td className="py-1.5 text-right tabular-nums">
                        {l.lines_estimated && <span className="text-muted" title="Includes size-based estimates">≈</span>}
                        {formatCount(l.lines)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-muted">{formatBytes(l.bytes)}</td>
                      <td className="py-1.5 text-right tabular-nums">{((100 * l.bytes) / totalBytes).toFixed(1)}%</td>
                      <td className="py-1.5 text-right tabular-nums text-muted">
                        {commented ? `${((100 * l.comment_lines) / commented).toFixed(0)}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {languages.github_breakdown.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <h3 className="mb-2 text-xs font-medium text-muted">GitHub linguist breakdown (for comparison)</h3>
          <StackedBar
            label="GitHub language share"
            format={formatBytes}
            segments={languages.github_breakdown.map((g) => ({
              key: g.language,
              label: g.language,
              value: g.bytes,
              color: languageColor(g.language),
            }))}
          />
        </div>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-muted">Extensions and methodology</summary>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {languages.extensions.map((e) => (
            <Badge key={e.extension}>
              <span className="font-mono">{e.extension}</span> {formatInteger(e.files)}
            </Badge>
          ))}
        </div>
        <div className="mt-2">
          <Note>{languages.methodology}</Note>
        </div>
      </details>
    </Panel>
  );
}
