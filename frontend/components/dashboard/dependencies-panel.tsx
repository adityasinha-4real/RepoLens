"use client";

import { useMemo, useState } from "react";
import type { DependencyAnalysis } from "@/lib/api/types";
import { formatInteger } from "@/lib/format";
import { AlertIcon } from "../ui/icons";
import { Badge, Empty, Note, Panel } from "../ui/primitives";

const SCOPE_TONE: Record<string, "good" | "info" | "neutral" | "warn"> = {
  production: "good",
  development: "info",
  optional: "neutral",
  peer: "neutral",
  build: "neutral",
};
const CONSTRAINT_LABEL: Record<string, string> = {
  exact: "pinned",
  range: "range",
  none: "unconstrained",
  managed: "managed",
  external: "external",
};

export function DependenciesPanel({ deps }: { deps: DependencyAnalysis }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [ecosystem, setEcosystem] = useState("all");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return deps.dependencies.filter(
      (d) =>
        (scope === "all" || d.scope === scope) &&
        (ecosystem === "all" || d.ecosystem === ecosystem) &&
        (!q || d.name.toLowerCase().includes(q) || d.manifest.toLowerCase().includes(q)),
    );
  }, [deps.dependencies, query, scope, ecosystem]);
  const scopes = [...new Set(deps.dependencies.map((d) => d.scope))];

  return (
    <Panel
      id="dependencies"
      title="Dependencies"
      description={`${formatInteger(deps.total)} declarations (${formatInteger(deps.unique_packages)} unique packages) in ${deps.manifests.length} manifest(s).`}
    >
      {deps.manifests.length === 0 ? (
        <Empty>No supported dependency manifests were found.</Empty>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {deps.ecosystems.map((e) => (
              <div key={e.ecosystem} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{e.ecosystem}</span>
                  <Badge tone={e.has_lockfile ? "good" : "warn"}>{e.has_lockfile ? "lockfile" : "no lockfile"}</Badge>
                </div>
                <div className="mt-1 text-xs text-muted tabular-nums">
                  {formatInteger(e.dependencies)} deps · {formatInteger(e.production)} prod · {formatInteger(e.development)} dev
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search packages or manifests…"
              aria-label="Search dependencies"
              className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-accent"
            />
            <select aria-label="Filter by scope" value={scope} onChange={(e) => setScope(e.target.value)}
              className="h-8 rounded-md border border-border bg-surface px-2 text-sm">
              <option value="all">All scopes</option>
              {scopes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            {deps.ecosystems.length > 1 && (
              <select aria-label="Filter by ecosystem" value={ecosystem} onChange={(e) => setEcosystem(e.target.value)}
                className="h-8 rounded-md border border-border bg-surface px-2 text-sm">
                <option value="all">All ecosystems</option>
                {deps.ecosystems.map((e) => <option key={e.ecosystem} value={e.ecosystem}>{e.ecosystem}</option>)}
              </select>
            )}
          </div>

          <div className="mt-2 max-h-96 overflow-auto rounded-md border border-border">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-3 py-1.5 font-medium">Package</th>
                  <th className="px-3 py-1.5 font-medium">Version</th>
                  <th className="px-3 py-1.5 font-medium">Scope</th>
                  <th className="px-3 py-1.5 font-medium">Ecosystem</th>
                  <th className="px-3 py-1.5 font-medium">Manifest</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 500).map((d, i) => (
                  <tr key={`${d.manifest}:${d.name}:${d.scope}:${i}`} className="border-b border-border/60 last:border-0">
                    <td className="px-3 py-1.5 font-mono text-xs">{d.name}</td>
                    <td className="px-3 py-1.5">
                      <span className="font-mono text-xs">{d.version ?? "—"}</span>{" "}
                      {d.constraint !== "range" && (
                        <Badge tone={d.constraint === "none" ? "warn" : "neutral"}>{CONSTRAINT_LABEL[d.constraint]}</Badge>
                      )}
                      {!d.direct && <Badge>indirect</Badge>}
                    </td>
                    <td className="px-3 py-1.5"><Badge tone={SCOPE_TONE[d.scope] ?? "neutral"}>{d.scope}</Badge></td>
                    <td className="px-3 py-1.5 text-xs text-muted">{d.ecosystem}</td>
                    <td className="max-w-[14rem] truncate px-3 py-1.5 font-mono text-xs text-muted" title={d.manifest}>{d.manifest}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && <Empty>No dependencies match the filters.</Empty>}
          </div>
          <p className="mt-1 text-xs text-muted">
            Showing {formatInteger(Math.min(filtered.length, 500))} of {formatInteger(filtered.length)}
            {deps.dependencies_truncated && " (report capped at 2,000 declarations)"}.
          </p>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted">Hygiene</h3>
              <ul className="space-y-1 text-sm">
                <li>{formatInteger(deps.unconstrained)} without a version constraint</li>
                <li>{formatInteger(deps.external_sources)} from git, path or URL sources</li>
                <li>{deps.lockfiles.length ? `Lockfiles: ${deps.lockfiles.slice(0, 4).join(", ")}` : "No lockfiles"}</li>
              </ul>
            </div>
            {deps.version_conflicts.length > 0 && (
              <div>
                <h3 className="mb-2 text-xs font-medium text-muted">Declared with different versions</h3>
                <ul className="space-y-1 text-xs">
                  {deps.version_conflicts.slice(0, 6).map((c) => (
                    <li key={`${c.ecosystem}:${c.name}`} title={c.manifests.join("\n")}>
                      <span className="font-mono">{c.name}</span>{" "}
                      <span className="text-muted">{c.versions.join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {deps.manifests.some((m) => m.parse_error) && (
            <ul className="mt-3 space-y-1 text-xs text-bad">
              {deps.manifests.filter((m) => m.parse_error).map((m) => (
                <li key={m.path}>Could not parse {m.path}: {m.parse_error}</li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="mt-4 flex items-start gap-2 rounded-md bg-subtle p-3">
        <AlertIcon size={14} className="mt-0.5 shrink-0 text-muted" />
        <Note>
          {deps.vulnerability_data} {deps.notes.join(" ")}
        </Note>
      </div>
    </Panel>
  );
}
