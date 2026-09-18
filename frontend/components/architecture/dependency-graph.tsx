"use client";

import { useMemo, useState } from "react";
import { layoutGraph, NODE_H, NODE_W } from "@/lib/graph-layout";
import { cx } from "../ui/primitives";

export interface GraphNode {
  id: string;
  label: string;
  sublabel?: string;
  tone?: string; // CSS color for the left accent
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

/** Interactive layered graph: click (or focus + Enter) a node to highlight its relationships. */
export function DependencyGraph({
  nodes,
  edges,
  selected,
  onSelect,
  ariaLabel,
  edgeLabel = (w) => `${w} import${w === 1 ? "" : "s"}`,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  ariaLabel: string;
  edgeLabel?: (weight: number) => string;
}) {
  const layout = useMemo(() => layoutGraph({ nodes, edges }), [nodes, edges]);
  const pos = useMemo(() => new Map(layout.nodes.map((n) => [n.id, n])), [layout]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const [hovered, setHovered] = useState<string | null>(null);
  const focus = hovered ?? selected;
  const maxWeight = Math.max(1, ...edges.map((e) => e.weight));
  const related = useMemo(() => {
    if (!focus) return null;
    const set = new Set([focus]);
    for (const e of layout.edges) {
      if (e.source === focus) set.add(e.target);
      if (e.target === focus) set.add(e.source);
    }
    return set;
  }, [focus, layout.edges]);

  return (
    <div className="overflow-x-auto rounded-md border border-border bg-subtle/40">
      <svg
        role="group"
        aria-label={ariaLabel}
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="mx-auto block"
        onClick={(e) => {
          if (e.target === e.currentTarget) onSelect(null);
        }}
      >
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 10 5 0 10z" fill="currentColor" />
          </marker>
        </defs>
        {layout.edges.map((e) => {
          const a = pos.get(e.source)!;
          const b = pos.get(e.target)!;
          const active = focus !== null && (e.source === focus || e.target === focus);
          const dim = focus !== null && !active;
          const x1 = a.x;
          const y1 = e.backEdge ? a.y - NODE_H / 2 : a.y + NODE_H / 2;
          const x2 = b.x;
          const y2 = e.backEdge ? b.y + NODE_H / 2 : b.y - NODE_H / 2;
          const bend = Math.max(30, Math.abs(y2 - y1) / 2);
          const d = e.backEdge
            ? `M${x1},${y1} C${x1 + 40},${y1 - bend} ${x2 + 40},${y2 + bend} ${x2},${y2}`
            : `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`;
          return (
            <path
              key={`${e.source}->${e.target}`}
              d={d}
              fill="none"
              markerEnd="url(#arrow)"
              strokeDasharray={e.backEdge ? "4 3" : undefined}
              strokeWidth={1 + (2.5 * e.weight) / maxWeight}
              className={cx(
                "transition-opacity",
                active ? "text-accent" : "text-muted",
                dim ? "opacity-10" : active ? "opacity-100" : "opacity-45",
              )}
              stroke="currentColor"
            >
              <title>
                {byId.get(e.source)?.label} → {byId.get(e.target)?.label}: {edgeLabel(e.weight)}
                {e.backEdge ? " (part of a cycle)" : ""}
              </title>
            </path>
          );
        })}
        {layout.nodes.map((n) => {
          const node = byId.get(n.id)!;
          const isSelected = selected === n.id;
          const dim = related !== null && !related.has(n.id);
          return (
            <g
              key={n.id}
              transform={`translate(${n.x - NODE_W / 2},${n.y - NODE_H / 2})`}
              role="button"
              tabIndex={0}
              aria-pressed={isSelected}
              aria-label={`${node.label}${node.sublabel ? `, ${node.sublabel}` : ""}`}
              className={cx("cursor-pointer outline-none transition-opacity", dim && "opacity-30")}
              onClick={() => onSelect(isSelected ? null : n.id)}
              onKeyDown={(ev) => {
                if (ev.key === "Enter" || ev.key === " ") {
                  ev.preventDefault();
                  onSelect(isSelected ? null : n.id);
                }
              }}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(n.id)}
              onBlur={() => setHovered(null)}
            >
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={6}
                className={cx("fill-[var(--surface)]", isSelected ? "stroke-[var(--accent)]" : "stroke-[var(--border)]")}
                strokeWidth={isSelected ? 2 : 1}
              />
              <rect width={3} height={NODE_H - 12} x={6} y={6} rx={1.5} fill={node.tone ?? "var(--muted)"} />
              <text x={16} y={17} className="fill-[var(--foreground)] font-mono text-[11px]">
                {truncate(node.label, 21)}
              </text>
              {node.sublabel && (
                <text x={16} y={31} className="fill-[var(--muted)] text-[10px]">
                  {truncate(node.sublabel, 26)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
