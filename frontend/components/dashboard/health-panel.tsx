"use client";

import { useState } from "react";
import type { HealthReport } from "@/lib/api/types";
import { ScoreBar } from "../charts/charts";
import { CheckIcon, ChevronIcon, XIcon } from "../ui/icons";
import { Badge, Note, Panel, cx } from "../ui/primitives";

export function HealthPanel({ health }: { health: HealthReport }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Panel
      id="health"
      title="Repository health"
      description="Measurable indicators built from explicit checks. Expand a dimension to see every check and its evidence."
      actions={
        health.overall !== null && health.overall !== undefined ? (
          <div className="text-right">
            <div className="text-2xl font-semibold tabular-nums leading-none">{health.overall}</div>
            <div className="text-[11px] text-muted">mean of dimensions</div>
          </div>
        ) : null
      }
    >
      <ul className="divide-y divide-border">
        {health.dimensions.map((d) => {
          const expanded = open === d.key;
          return (
            <li key={d.key}>
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : d.key)}
                aria-expanded={expanded}
                className="grid w-full grid-cols-[1rem_minmax(0,10rem)_minmax(0,1fr)_3rem] items-center gap-3 py-2.5 text-left text-sm hover:bg-subtle/60"
              >
                <ChevronIcon
                  size={14}
                  className={cx("text-muted transition-transform", expanded && "rotate-90")}
                />
                <span className="truncate font-medium">{d.label}</span>
                <ScoreBar score={d.applicable ? (d.score ?? null) : null} label={`${d.label} score`} />
                <span className="text-right tabular-nums">
                  {d.applicable ? d.score : <span className="text-xs text-muted">n/a</span>}
                </span>
              </button>
              {expanded && (
                <div className="pb-3 pl-7">
                  <p className="text-xs text-muted">{d.summary}</p>
                  <table className="mt-2 w-full text-sm">
                    <thead className="sr-only">
                      <tr>
                        <th>Result</th>
                        <th>Check</th>
                        <th>Evidence</th>
                        <th>Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.checks.map((c) => (
                        <tr key={c.id} className="align-top">
                          <td className="w-6 py-1">
                            {c.passed ? (
                              <CheckIcon size={14} className="text-good" aria-label="passed" />
                            ) : (
                              <XIcon size={14} className="text-bad" aria-label="not passed" />
                            )}
                          </td>
                          <td className="py-1 pr-3">{c.label}</td>
                          <td className="py-1 pr-3 text-xs text-muted">{c.detail}</td>
                          <td className="whitespace-nowrap py-1 text-right text-xs tabular-nums text-muted">
                            {c.points}/{c.max_points}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex gap-2">
        <Badge>No AI scoring</Badge>
        <Note>{health.methodology}</Note>
      </div>
    </Panel>
  );
}
