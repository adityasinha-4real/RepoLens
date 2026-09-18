import type { AnalysisReport } from "@/lib/api/types";
import { formatBytes, formatCount } from "@/lib/format";
import { Panel, Stat } from "../ui/primitives";
import { RepositoryHeader } from "./repository-header";

export function Dashboard({ report }: { report: AnalysisReport }) {
  const s = report.structure;
  return (
    <div className="space-y-6">
      <RepositoryHeader report={report} />
      <Panel id="overview" title="Overview">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Files" value={formatCount(s.total_files)} />
          <Stat label="Directories" value={formatCount(s.total_directories)} />
          <Stat label="Size on disk" value={formatBytes(s.total_size_bytes)} />
          <Stat label="Languages" value={formatCount(report.languages.languages.length)} />
          <Stat label="Dependencies" value={formatCount(report.dependencies.total)} />
          <Stat label="Health indicator" value={report.health.overall ?? "—"} />
        </dl>
      </Panel>
    </div>
  );
}
