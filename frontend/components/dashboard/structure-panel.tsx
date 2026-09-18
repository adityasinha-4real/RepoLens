import type { AnalysisReport } from "@/lib/api/types";
import { CATEGORY_COLORS } from "@/lib/colors";
import { formatBytes, formatInteger } from "@/lib/format";
import { BarList, StackedBar } from "../charts/charts";
import { Note, Panel } from "../ui/primitives";
import { FileTree } from "./file-tree";

export function StructurePanel({ report }: { report: AnalysisReport }) {
  const s = report.structure;
  return (
    <Panel
      id="structure"
      title="Structure"
      description={`${formatInteger(s.analyzed_files)} analyzed files in ${formatInteger(s.total_directories)} directories · ${formatInteger(s.ignored_files)} files in generated/vendored directories are counted but not analyzed.`}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0">
          <FileTree root={s.tree} htmlUrl={report.repository.html_url} sha={report.analysis.commit_sha} />
          <div className="mt-2">
            <Note>
              Showing up to {formatInteger(s.tree_node_budget)} entries, breadth-first.
              {s.truncated && " GitHub returned a truncated tree for this repository."}
            </Note>
          </div>
        </div>
        <div className="min-w-0 space-y-5">
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted">File categories</h3>
            <StackedBar
              label="Files by category"
              segments={s.categories.map((c) => ({
                key: c.category,
                label: c.category,
                value: c.files,
                color: CATEGORY_COLORS[c.category] ?? "#94a3b8",
              }))}
            />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted">Largest directories</h3>
            <BarList
              format={formatBytes}
              items={s.largest_directories.slice(0, 6).map((d) => ({
                key: d.path,
                label: <span className="font-mono text-xs">{d.path}/</span>,
                value: d.bytes,
                hint: `· ${formatInteger(d.files)} files`,
              }))}
            />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted">Largest files</h3>
            <BarList
              format={formatBytes}
              items={s.largest_files.slice(0, 6).map((f) => ({
                key: f.path,
                label: <span className="font-mono text-xs">{f.path}</span>,
                value: f.size,
              }))}
            />
          </div>
          {s.ignored_directories.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted">Ignored (generated / vendored) directories</h3>
              <ul className="space-y-1 text-xs">
                {s.ignored_directories.slice(0, 6).map((d) => (
                  <li key={d.path} className="flex justify-between gap-2">
                    <span className="truncate font-mono">{d.path}/</span>
                    <span className="shrink-0 tabular-nums text-muted">
                      {formatInteger(d.files)} files · {formatBytes(d.bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(s.submodules.length > 0 || s.symlinks > 0) && (
            <Note>
              {s.submodules.length > 0 && `${s.submodules.length} git submodule(s) not followed. `}
              {s.symlinks > 0 && `${s.symlinks} symlink(s).`}
            </Note>
          )}
        </div>
      </div>
    </Panel>
  );
}
