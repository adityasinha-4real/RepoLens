import type { AnalysisReport } from "@/lib/api/types";
import { ArchitecturePanel } from "../architecture/architecture-panel";
import { AISummaryPanel } from "./ai-summary-panel";
import { DependenciesPanel } from "./dependencies-panel";
import { DocumentationPanel } from "./documentation-panel";
import { HealthPanel } from "./health-panel";
import { LanguagesPanel } from "./languages-panel";
import { OverviewPanel } from "./overview-panel";
import { QualityPanel } from "./quality-panel";
import { RepositoryHeader } from "./repository-header";
import { SecurityPanel } from "./security-panel";
import { SectionNav } from "./section-nav";
import { StructurePanel } from "./structure-panel";

export function Dashboard({ report }: { report: AnalysisReport }) {
  return (
    <div className="space-y-5">
      <RepositoryHeader report={report} />
      <SectionNav
        sections={[
          { id: "overview", label: "Overview" },
          { id: "health", label: "Health" },
          { id: "structure", label: "Structure" },
          { id: "languages", label: "Languages", count: report.languages.languages.length },
          { id: "dependencies", label: "Dependencies", count: report.dependencies.total },
          { id: "quality", label: "Code quality", count: report.quality.high_complexity_count },
          { id: "security", label: "Security", count: report.security.findings.filter((f) => !f.in_test).length },
          { id: "documentation", label: "Documentation" },
          { id: "architecture", label: "Architecture", count: report.architecture.modules.length },
        ]}
      />
      <OverviewPanel report={report} />
      <AISummaryPanel repositoryUrl={report.repository.html_url} />
      <HealthPanel health={report.health} />
      <StructurePanel report={report} />
      <div className="grid gap-5 xl:grid-cols-2">
        <LanguagesPanel languages={report.languages} />
        <DocumentationPanel doc={report.documentation} />
      </div>
      <QualityPanel report={report} />
      <SecurityPanel report={report} />
      <ArchitecturePanel arch={report.architecture} />
      <DependenciesPanel deps={report.dependencies} />
    </div>
  );
}
