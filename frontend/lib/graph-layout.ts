// Deterministic layered layout for directed graphs (importer above imported).
// Pure function, no dependencies, so it is easy to test and renders identically everywhere.

export interface LayoutInput {
  nodes: { id: string }[];
  edges: { source: string; target: string; weight: number }[];
}

export interface PositionedNode {
  id: string;
  x: number; // center
  y: number; // center
  layer: number;
}

export interface PositionedEdge {
  source: string;
  target: string;
  weight: number;
  backEdge: boolean; // part of a cycle; drawn upward/dashed
}

export interface Layout {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
  width: number;
  height: number;
}

export const NODE_W = 168;
export const NODE_H = 40;
const GAP_X = 28;
const GAP_Y = 64;
const PAD = 16;

export function layoutGraph(input: LayoutInput, maxPerRow = 6): Layout {
  const ids = input.nodes.map((n) => n.id).sort();
  const idSet = new Set(ids);
  const edges = input.edges.filter((e) => idSet.has(e.source) && idSet.has(e.target) && e.source !== e.target);
  const out = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of edges) out.get(e.source)!.push(e.target);
  for (const list of out.values()) list.sort();

  // 1. Find back edges with an iterative DFS (deterministic order) to break cycles.
  const state = new Map<string, 0 | 1 | 2>(ids.map((id) => [id, 0]));
  const back = new Set<string>();
  for (const start of ids) {
    if (state.get(start) !== 0) continue;
    const stack: [string, number][] = [[start, 0]];
    state.set(start, 1);
    while (stack.length) {
      const top = stack[stack.length - 1];
      const children = out.get(top[0])!;
      if (top[1] < children.length) {
        const child = children[top[1]++];
        const s = state.get(child);
        if (s === 1) back.add(JSON.stringify([top[0], child]));
        else if (s === 0) {
          state.set(child, 1);
          stack.push([child, 0]);
        }
      } else {
        state.set(top[0], 2);
        stack.pop();
      }
    }
  }
  const isBack = (e: { source: string; target: string }) => back.has(JSON.stringify([e.source, e.target]));

  // 2. Longest-path layering on the resulting DAG (Kahn's algorithm).
  const indeg = new Map<string, number>(ids.map((id) => [id, 0]));
  const dagOut = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of edges) {
    if (isBack(e)) continue;
    dagOut.get(e.source)!.push(e.target);
    indeg.set(e.target, indeg.get(e.target)! + 1);
  }
  const layer = new Map<string, number>(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => indeg.get(id) === 0);
  while (queue.length) {
    const id = queue.shift()!;
    for (const t of dagOut.get(id)!) {
      layer.set(t, Math.max(layer.get(t)!, layer.get(id)! + 1));
      indeg.set(t, indeg.get(t)! - 1);
      if (indeg.get(t) === 0) queue.push(t);
    }
  }

  // 3. Order within layers by barycenter of predecessors, then wrap wide layers into rows.
  const layers: string[][] = [];
  for (const id of ids) (layers[layer.get(id)!] ??= []).push(id);
  const order = new Map<string, number>();
  const preds = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of edges) if (!isBack(e)) preds.get(e.target)!.push(e.source);
  const rows: string[][] = [];
  const rowOf = new Map<string, number>();
  for (const members of layers.filter(Boolean)) {
    const bary = (id: string) => {
      const p = preds.get(id)!.filter((x) => order.has(x));
      return p.length ? p.reduce((s, x) => s + order.get(x)!, 0) / p.length : Number.POSITIVE_INFINITY;
    };
    members.sort((a, b) => bary(a) - bary(b) || a.localeCompare(b));
    for (let i = 0; i < members.length; i += maxPerRow) {
      const row = members.slice(i, i + maxPerRow);
      row.forEach((id, j) => {
        order.set(id, j);
        rowOf.set(id, rows.length);
      });
      rows.push(row);
    }
  }

  const widest = Math.max(1, ...rows.map((r) => r.length));
  const width = PAD * 2 + widest * NODE_W + (widest - 1) * GAP_X;
  const nodes: PositionedNode[] = [];
  rows.forEach((row, r) => {
    const rowWidth = row.length * NODE_W + (row.length - 1) * GAP_X;
    const left = (width - rowWidth) / 2;
    row.forEach((id, j) => {
      nodes.push({
        id,
        layer: layer.get(id)!,
        x: left + j * (NODE_W + GAP_X) + NODE_W / 2,
        y: PAD + r * (NODE_H + GAP_Y) + NODE_H / 2,
      });
    });
  });
  const height = PAD * 2 + rows.length * NODE_H + Math.max(0, rows.length - 1) * GAP_Y;
  return {
    nodes,
    edges: edges.map((e) => ({ ...e, backEdge: isBack(e) || rowOf.get(e.source)! >= rowOf.get(e.target)! })),
    width,
    height,
  };
}
