import { describe, expect, it } from "vitest";
import { layoutGraph } from "@/lib/graph-layout";

const n = (...ids: string[]) => ids.map((id) => ({ id }));

describe("layoutGraph", () => {
  it("places importers above the modules they import", () => {
    const layout = layoutGraph({
      nodes: n("api", "services", "models", "tests"),
      edges: [
        { source: "api", target: "services", weight: 3 },
        { source: "services", target: "models", weight: 1 },
        { source: "tests", target: "services", weight: 2 },
      ],
    });
    const y = Object.fromEntries(layout.nodes.map((p) => [p.id, p.y]));
    expect(y.api).toBeLessThan(y.services);
    expect(y.tests).toBeLessThan(y.services);
    expect(y.services).toBeLessThan(y.models);
    expect(layout.edges.every((e) => !e.backEdge)).toBe(true);
  });

  it("breaks cycles deterministically and marks the back edge", () => {
    const input = {
      nodes: n("a", "b", "c"),
      edges: [
        { source: "a", target: "b", weight: 1 },
        { source: "b", target: "c", weight: 1 },
        { source: "c", target: "a", weight: 1 },
      ],
    };
    const first = layoutGraph(input);
    expect(first.edges.filter((e) => e.backEdge)).toHaveLength(1);
    expect(layoutGraph(input)).toEqual(first); // deterministic
  });

  it("wraps wide layers into rows and ignores edges to unknown nodes", () => {
    const layout = layoutGraph(
      { nodes: n(...Array.from({ length: 10 }, (_, i) => `m${i}`)), edges: [{ source: "m0", target: "ghost", weight: 1 }] },
      4,
    );
    expect(new Set(layout.nodes.map((p) => p.y)).size).toBe(3);
    expect(layout.edges).toHaveLength(0);
    const xs = layout.nodes.map((p) => p.x);
    expect(Math.max(...xs)).toBeLessThan(layout.width);
  });
});
