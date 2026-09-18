"use client";

import { useMemo, useState } from "react";
import type { ArchitectureAnalysis } from "@/lib/api/types";
import { languageColor } from "@/lib/colors";
import { formatBytes, formatInteger } from "@/lib/format";
import { Badge, Empty, Note, Panel, cx } from "../ui/primitives";
import { DependencyGraph, type GraphNode } from "./dependency-graph";

const MAX_GRAPH_NODES = 30;

export function ArchitecturePanel({ arch }: { arch: ArchitectureAnalysis }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [connectedOnly, setConnectedOnly] = useState(arch.edges.length > 0);
  const modules = useMemo(() => new Map(arch.modules.map((m) => [m.id, m])), [arch.modules]);

  const connected = useMemo(() => {
    const ids = new Set<string>();
    for (const e of arch.edges) {
      ids.add(e.source);
      ids.add(e.target);
    }
    return ids;
  }, [arch.edges]);

  const graphNodes: GraphNode[] = useMemo(() => {
    const pool = arch.modules.filter((m) => !connectedOnly || connected.has(m.id));
    return pool
      .sort((a, b) => b.files - a.files)
      .slice(0, MAX_GRAPH_NODES)
      .map((m) => ({
        id: m.id,
        label: m.id === "." ? "(root)" : m.path,
        sublabel: `${m.role} · ${formatInteger(m.files)} files`,
        tone: m.languages[0] ? languageColor(m.languages[0]) : undefined,
      }));
  }, [arch.modules, connected, connectedOnly]);
  const shownIds = new Set(graphNodes.map((n) => n.id));
  const graphEdges = arch.edges
    .filter((e) => shownIds.has(e.source) && shownIds.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, weight: e.imports }));
  const hiddenCount = arch.modules.length - graphNodes.length;
  const res = arch.import_resolution;
  const current = selected ? modules.get(selected) : null;

  return (
    <Panel
      id="architecture"
      title="Architecture"
      description="Module relationships come only from import statements that resolved to files in this repository. Roles are inferred from directory names."
      actions={
        arch.edges.length > 0 ? (
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input type="checkbox" checked={connectedOnly} onChange={(e) => setConnectedOnly(e.target.checked)} />
            Connected modules only
          </label>
        ) : null
      }
    >
      <div className="mb-4 flex flex-wrap gap-1.5">
        {arch.project_types.map((t) => (
          <Badge key={t.name} tone="accent" title={t.evidence}>{t.name}</Badge>
        ))}
        {arch.frameworks.map((f) => (
          <Badge key={f.name} title={`${f.category} · detected from ${f.evidence}`}>{f.name}</Badge>
        ))}
        {arch.monorepo_tool && <Badge tone="info">{arch.monorepo_tool} · {arch.workspace_packages.length} packages</Badge>}
      </div>

      {graphNodes.length === 0 ? (
        <Empty>No modules to display.</Empty>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="min-w-0">
            <DependencyGraph
              nodes={graphNodes}
              edges={graphEdges}
              selected={selected}
              onSelect={setSelected}
              ariaLabel="Module dependency graph"
            />
            <div className="mt-2">
              <Note>
                Arrows point from the importing module to the imported one. Line width reflects the number of
                resolved imports and dashed lines close a cycle.
                {hiddenCount > 0 && ` ${hiddenCount} smaller or unconnected module(s) are not drawn.`}
                {arch.edges.length === 0 && " No cross-module imports were resolved, so no relationships are drawn."}
              </Note>
            </div>
          </div>
          <aside className="rounded-md border border-border p-3 text-sm" aria-live="polite">
            {current ? (
              <ModuleDetails arch={arch} id={current.id} onSelect={setSelected} />
            ) : (
              <div className="space-y-2 text-xs text-muted">
                <p>Select a module to see its details and relationships.</p>
                <p>
                  Imports analyzed in {formatInteger(res.files_parsed)} downloaded files
                  {res.languages.length > 0 && ` (${res.languages.join(", ")})`}: {formatInteger(res.internal_resolved)} internal,{" "}
                  {formatInteger(res.external)} external, {formatInteger(res.unresolved)} unresolved or ambiguous.
                </p>
              </div>
            )}
          </aside>
        </div>
      )}

      <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">Entry points</h3>
          {arch.entry_points.length ? (
            <ul className="space-y-1.5 text-sm">
              {arch.entry_points.slice(0, 10).map((e) => (
                <li key={e.path} className="min-w-0">
                  <span className="block truncate font-mono text-xs" title={e.path}>{e.path}</span>
                  <span className="text-xs text-muted">{e.kind} · {e.evidence}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No entry points identified.</p>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">Most imported files</h3>
          {arch.hubs.length ? (
            <ul className="space-y-1 text-sm">
              {arch.hubs.map((h) => (
                <li key={h.path} className="flex justify-between gap-2">
                  <span className="truncate font-mono text-xs" title={h.path}>{h.path}</span>
                  <span className="shrink-0 text-xs tabular-nums text-muted">{h.imported_by} importers</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No internal imports resolved.</p>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">Infrastructure</h3>
          {arch.infrastructure.length ? (
            <ul className="space-y-1 text-sm">
              {arch.infrastructure.slice(0, 10).map((i) => (
                <li key={`${i.kind}:${i.path}`} className="min-w-0">
                  <span className="font-medium">{i.kind}</span>{" "}
                  <span className="font-mono text-xs text-muted">{i.path}</span>
                  <span className="block text-xs text-muted">{i.detail}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No container, orchestration or IaC files found.</p>
          )}
        </div>
      </div>

      {arch.compose_services.length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-medium text-muted">Docker Compose services (depends_on)</h3>
          <ComposeGraph arch={arch} />
        </div>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-muted">All modules and methodology</summary>
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr className="border-b border-border">
              <th className="py-1 font-medium">Module</th>
              <th className="py-1 font-medium">Role</th>
              <th className="py-1 text-right font-medium">Files</th>
              <th className="py-1 text-right font-medium">Size</th>
            </tr>
          </thead>
          <tbody>
            {arch.modules.map((m) => (
              <tr key={m.id} className="border-b border-border/60 last:border-0">
                <td className="py-1 font-mono text-xs">{m.id === "." ? "(root)" : m.path}</td>
                <td className="py-1 text-xs">
                  {m.role} <span className="text-muted">({m.role_source.replace("-", " ")})</span>
                </td>
                <td className="py-1 text-right tabular-nums">{formatInteger(m.files)}</td>
                <td className="py-1 text-right tabular-nums text-muted">{formatBytes(m.bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2">
          <Note>{arch.methodology} {arch.notes.join(" ")}</Note>
        </div>
      </details>
    </Panel>
  );
}

function ModuleDetails({ arch, id, onSelect }: { arch: ArchitectureAnalysis; id: string; onSelect: (id: string) => void }) {
  const m = arch.modules.find((x) => x.id === id)!;
  const outgoing = arch.edges.filter((e) => e.source === id).sort((a, b) => b.imports - a.imports);
  const incoming = arch.edges.filter((e) => e.target === id).sort((a, b) => b.imports - a.imports);
  const link = (target: string, count: number) => (
    <li key={target}>
      <button type="button" onClick={() => onSelect(target)} className="font-mono text-xs hover:text-accent">
        {target === "." ? "(root)" : target}
      </button>{" "}
      <span className="text-xs text-muted">({count})</span>
    </li>
  );
  return (
    <div>
      <p className="break-all font-mono text-sm font-medium">{m.id === "." ? "(root)" : m.path}</p>
      <p className="mt-0.5 text-xs text-muted">
        {m.role}{" "}
        <span className={cx(m.role_source === "unknown" && "italic")}>
          ({m.role_source === "directory-name" ? "inferred from name" : m.role_source.replace("-", " ")})
        </span>
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><dt className="text-muted">Files</dt><dd className="tabular-nums">{formatInteger(m.files)}</dd></div>
        <div><dt className="text-muted">Source files</dt><dd className="tabular-nums">{formatInteger(m.source_files)}</dd></div>
        <div><dt className="text-muted">Size</dt><dd className="tabular-nums">{formatBytes(m.bytes)}</dd></div>
        <div><dt className="text-muted">Downloaded</dt><dd className="tabular-nums">{formatInteger(m.sampled_files)}</dd></div>
      </dl>
      {m.languages.length > 0 && <p className="mt-2 text-xs">{m.languages.join(", ")}</p>}
      <h4 className="mt-3 text-xs font-medium text-muted">Imports from ({outgoing.length})</h4>
      <ul className="mt-1 space-y-0.5">{outgoing.slice(0, 10).map((e) => link(e.target, e.imports))}</ul>
      <h4 className="mt-3 text-xs font-medium text-muted">Imported by ({incoming.length})</h4>
      <ul className="mt-1 space-y-0.5">{incoming.slice(0, 10).map((e) => link(e.source, e.imports))}</ul>
    </div>
  );
}

function ComposeGraph({ arch }: { arch: ArchitectureAnalysis }) {
  const [selected, setSelected] = useState<string | null>(null);
  const names = new Set(arch.compose_services.map((s) => s.name));
  const nodes = arch.compose_services.map((s) => ({
    id: s.name,
    label: s.name,
    sublabel: s.image ?? (s.build ? "built locally" : undefined),
  }));
  const edges = arch.compose_services.flatMap((s) =>
    (s.depends_on ?? []).filter((d) => names.has(d)).map((d) => ({ source: s.name, target: d, weight: 1 })),
  );
  return (
    <DependencyGraph
      nodes={nodes}
      edges={edges}
      selected={selected}
      onSelect={setSelected}
      ariaLabel="Docker Compose service dependencies"
      edgeLabel={() => "depends_on"}
    />
  );
}
