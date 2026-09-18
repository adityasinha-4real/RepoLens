import type { AnalysisReport } from "@/lib/api/types";
import { formatBytes, formatCount, formatDate } from "@/lib/format";
import { Badge, Panel, Stat } from "../ui/primitives";

export function OverviewPanel({ report }: { report: AnalysisReport }) {
  const { structure: s, languages: l, dependencies: d, documentation: doc, analysis: a } = report;
  const repo = report.repository;
  const docFiles = doc.files.filter((f) => f.present).length;
  return (
    <Panel id="overview" title="Overview">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Files" value={formatCount(s.total_files)} hint={`${formatCount(s.ignored_files)} in ignored dirs`} />
        <Stat label="Directories" value={formatCount(s.total_directories)} hint={`max depth ${s.max_depth}`} />
        <Stat label="Size (tree)" value={formatBytes(s.total_size_bytes)} hint={`GitHub: ${formatBytes(repo.size_kb * 1024)} incl. history`} />
        <Stat
          label="Lines of code"
          value={formatCount(l.total_lines)}
          hint={l.estimated_lines > 0 ? `${formatCount(l.counted_lines)} counted, rest estimated` : "all counted"}
        />
        <Stat label="Languages" value={formatCount(l.languages.length)} hint={l.primary_language ?? undefined} />
        <Stat
          label="Dependencies"
          value={formatCount(d.total)}
          hint={`${formatCount(d.production)} prod · ${formatCount(d.development)} dev`}
        />
      </dl>
      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4 text-xs">
        <Badge tone={doc.readme ? "good" : "bad"}>{doc.readme ? "README" : "No README"}</Badge>
        <Badge tone={repo.license_spdx ? "good" : "warn"}>{repo.license_spdx ?? "No license detected"}</Badge>
        <Badge>{docFiles} community files</Badge>
        {report.architecture.project_types.map((t) => (
          <Badge key={t.name} tone="accent" title={t.evidence}>
            {t.name}
          </Badge>
        ))}
        <span className="ml-auto text-muted">
          Created {formatDate(repo.created_at)} · commit{" "}
          <a
            className="font-mono hover:text-accent"
            href={`${repo.html_url}/tree/${a.commit_sha}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {a.commit_sha.slice(0, 7)}
          </a>{" "}
          · {formatCount(a.fetch.files_downloaded)} files read in {(a.duration_ms / 1000).toFixed(1)}s
        </span>
      </div>
      {a.notes.length > 0 && (
        <ul className="mt-3 space-y-1 rounded-md border border-warn/30 bg-warn/5 p-3 text-xs">
          {a.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
