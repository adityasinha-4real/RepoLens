"use client";

import { useMemo, useState } from "react";
import type { TreeNode } from "@/lib/api/types";
import { formatBytes, formatInteger } from "@/lib/format";
import { ChevronIcon, FileIcon, FolderIcon, LinkIcon } from "../ui/icons";
import { Badge, cx } from "../ui/primitives";

function flatten(node: TreeNode, out: TreeNode[] = []): TreeNode[] {
  for (const child of node.children ?? []) {
    out.push(child);
    flatten(child, out);
  }
  return out;
}

export function FileTree({ root, htmlUrl, sha }: { root: TreeNode; htmlUrl: string; sha: string }) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [query, setQuery] = useState("");
  const all = useMemo(() => flatten(root), [root]);
  const q = query.trim().toLowerCase();
  const matches = q ? all.filter((n) => n.path.toLowerCase().includes(q)).slice(0, 200) : [];

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const expandAll = () =>
    setExpanded(new Set(all.filter((n) => n.type === "dir" && !n.ignored).map((n) => n.path)));

  return (
    <div>
      <div className="mb-2 flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter files and folders…"
          aria-label="Filter the file tree"
          className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-accent"
        />
        <button type="button" onClick={expandAll} className="h-8 rounded-md border border-border px-2 text-xs hover:bg-subtle">
          Expand all
        </button>
        <button type="button" onClick={() => setExpanded(new Set())} className="h-8 rounded-md border border-border px-2 text-xs hover:bg-subtle">
          Collapse
        </button>
      </div>
      <div className="max-h-[28rem] overflow-auto rounded-md border border-border py-1 font-mono text-[13px]">
        {q ? (
          matches.length ? (
            <ul aria-label="Matching paths">
              {matches.map((n) => (
                <li key={n.path} className="flex items-center gap-2 px-2 py-0.5">
                  <NodeIcon node={n} />
                  <span className="truncate">{n.path}</span>
                  <NodeMeta node={n} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-4 text-center font-sans text-sm text-muted">No matching paths in the loaded tree.</p>
          )
        ) : (
          <Branch nodes={root.children ?? []} omitted={root.omitted_children} depth={0}
            expanded={expanded} toggle={toggle} htmlUrl={htmlUrl} sha={sha} />
        )}
      </div>
    </div>
  );
}

function Branch({
  nodes, omitted, depth, expanded, toggle, htmlUrl, sha,
}: {
  nodes: TreeNode[];
  omitted: number;
  depth: number;
  expanded: Set<string>;
  toggle: (path: string) => void;
  htmlUrl: string;
  sha: string;
}) {
  return (
    <ul role={depth === 0 ? "tree" : "group"} aria-label={depth === 0 ? "Repository files" : undefined}>
      {nodes.map((node) => {
        const isDir = node.type === "dir";
        const open = expanded.has(node.path);
        const canOpen = isDir && !node.ignored && (node.children?.length ?? 0) + node.omitted_children > 0;
        return (
          <li key={node.path} role="treeitem" aria-expanded={canOpen ? open : undefined} aria-selected={false}>
            <div className="group flex items-center gap-1.5 px-2 py-0.5 hover:bg-subtle" style={{ paddingLeft: `${0.5 + depth * 1.1}rem` }}>
              {canOpen ? (
                <button
                  type="button"
                  onClick={() => toggle(node.path)}
                  className="flex min-w-0 items-center gap-1.5"
                  aria-label={`${open ? "Collapse" : "Expand"} ${node.name}`}
                >
                  <ChevronIcon size={12} className={cx("shrink-0 text-muted transition-transform", open && "rotate-90")} />
                  <NodeIcon node={node} />
                  <span className="truncate">{node.name}</span>
                </button>
              ) : (
                <span className="flex min-w-0 items-center gap-1.5 pl-[18px]">
                  <NodeIcon node={node} />
                  {node.type === "file" ? (
                    <a
                      href={`${htmlUrl}/blob/${sha}/${node.path.split("/").map(encodeURIComponent).join("/")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="truncate hover:text-accent hover:underline"
                    >
                      {node.name}
                    </a>
                  ) : (
                    <span className={cx("truncate", node.ignored && "text-muted")}>{node.name}</span>
                  )}
                </span>
              )}
              <NodeMeta node={node} />
            </div>
            {canOpen && open && (
              <Branch nodes={node.children ?? []} omitted={node.omitted_children} depth={depth + 1}
                expanded={expanded} toggle={toggle} htmlUrl={htmlUrl} sha={sha} />
            )}
          </li>
        );
      })}
      {omitted > 0 && (
        <li className="px-2 py-0.5 font-sans text-xs text-muted" style={{ paddingLeft: `${1.6 + depth * 1.1}rem` }}>
          … {formatInteger(omitted)} more not shown (display limit)
        </li>
      )}
    </ul>
  );
}

function NodeIcon({ node }: { node: TreeNode }) {
  if (node.type === "dir") return <FolderIcon size={14} className={cx("shrink-0", node.ignored ? "text-muted" : "text-accent")} />;
  if (node.type === "symlink" || node.type === "submodule") return <LinkIcon size={14} className="shrink-0 text-muted" />;
  return <FileIcon size={14} className="shrink-0 text-muted" />;
}

function NodeMeta({ node }: { node: TreeNode }) {
  return (
    <span className="ml-auto flex shrink-0 items-center gap-2 pl-2 font-sans text-[11px] text-muted">
      {node.ignored && <Badge tone="warn" title="Generated or vendored directory: counted but not analyzed">ignored</Badge>}
      {node.type === "submodule" && <Badge>submodule</Badge>}
      {node.type === "symlink" && <Badge>symlink</Badge>}
      {node.type === "dir" && <span className="tabular-nums">{formatInteger(node.files)} files</span>}
      {(node.type === "dir" || node.type === "file") && <span className="w-14 text-right tabular-nums">{formatBytes(node.size)}</span>}
    </span>
  );
}
