import type { AnalysisReport } from "@/lib/api/types";
import { formatCount, formatDateTime, formatRelative } from "@/lib/format";
import { ExternalIcon, ForkIcon, IssueIcon, StarIcon } from "../ui/icons";
import { Badge } from "../ui/primitives";
import { ExportMenu } from "./export-menu";

export function RepositoryHeader({ report }: { report: AnalysisReport }) {
  const repo = report.repository;
  const meta = report.analysis;
  return (
    <header className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">
            <span className="text-muted">{repo.owner}/</span>
            {repo.name}
          </h1>
          <a
            href={repo.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted hover:text-accent"
          >
            GitHub <ExternalIcon size={12} />
          </a>
          {repo.archived && <Badge tone="warn">Archived</Badge>}
          {repo.is_fork && <Badge>Fork</Badge>}
          {repo.is_template && <Badge>Template</Badge>}
          {meta.partial && (
            <Badge tone="warn" title={meta.notes.join(" ")}>
              Partial analysis
            </Badge>
          )}
        </div>
        {repo.description && <p className="mt-1 max-w-3xl text-sm text-muted">{repo.description}</p>}
        {repo.topics && repo.topics.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {repo.topics.slice(0, 10).map((t) => (
              <Badge key={t} tone="accent">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-start gap-3 lg:items-end">
      <ExportMenu report={report} />
      <dl className="flex shrink-0 flex-wrap gap-x-5 gap-y-2 text-sm">
        <Meta icon={<StarIcon size={14} />} label="Stars" value={formatCount(repo.stars)} />
        <Meta icon={<ForkIcon size={14} />} label="Forks" value={formatCount(repo.forks)} />
        <Meta
          icon={<IssueIcon size={14} />}
          label="Open issues + PRs"
          value={formatCount(repo.open_issues)}
        />
        <Meta label="Language" value={repo.primary_language ?? "—"} />
        <Meta label="Last push" value={formatRelative(repo.pushed_at)} />
        <Meta
          label="Analyzed"
          value={formatRelative(meta.analyzed_at)}
          title={`${formatDateTime(meta.analyzed_at)} · commit ${meta.commit_sha.slice(0, 7)}`}
        />
      </dl>
      </div>
    </header>
  );
}

function Meta({
  icon,
  label,
  value,
  title,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div title={title}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="flex items-center gap-1 font-medium tabular-nums">
        {icon && <span className="text-muted">{icon}</span>}
        {value}
      </dd>
    </div>
  );
}
