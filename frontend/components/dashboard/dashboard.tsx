import type { AnalysisReport } from "@/lib/api/types";
import { DependenciesPanel } from "./dependencies-panel";
import { DocumentationPanel } from "./documentation-panel";
import { HealthPanel } from "./health-panel";
import { LanguagesPanel } from "./languages-panel";
import { OverviewPanel } from "./overview-panel";
import { RepositoryHeader } from "./repository-header";
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
          { id: "documentation", label: "Documentation" },
        ]}
      />
      <OverviewPanel report={report} />
      <HealthPanel health={report.health} />
      <StructurePanel report={report} />
      <div className="grid gap-5 xl:grid-cols-2">
        <LanguagesPanel languages={report.languages} />
        <DocumentationPanel doc={report.documentation} />
      </div>
      <DependenciesPanel deps={report.dependencies} />
    </div>
  );
}
