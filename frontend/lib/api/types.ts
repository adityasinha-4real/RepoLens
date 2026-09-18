// Friendly aliases over the types generated from the backend's OpenAPI schema
// (lib/api/schema.gen.ts — regenerate with `npm run gen:types`).
import type { components } from "./schema.gen";

type S = components["schemas"];

export type AnalysisReport = S["AnalysisReport"];
export type RepositoryMetadata = S["RepositoryMetadata"];
export type AnalysisMeta = S["AnalysisMeta"];
export type HealthReport = S["HealthReport"];
export type HealthDimension = S["HealthDimension"];
export type HealthCheck = S["HealthCheck"];
export type StructureAnalysis = S["StructureAnalysis"];
export type TreeNode = S["TreeNode"];
export type LanguageAnalysis = S["LanguageAnalysis"];
export type LanguageStat = S["LanguageStat"];
export type DependencyAnalysis = S["DependencyAnalysis"];
export type Dependency = S["Dependency"];
export type QualityAnalysis = S["QualityAnalysis"];
export type ComplexityItem = S["ComplexityItem"];
export type DocumentationAnalysis = S["DocumentationAnalysis"];
export type SecurityAnalysis = S["SecurityAnalysis"];
export type SecurityFinding = S["SecurityFinding"];
export type ArchitectureAnalysis = S["ArchitectureAnalysis"];
export type ArchitectureModule = S["Module"];
export type ModuleEdge = S["ModuleEdge"];

export type ProgressStage = "validate" | "metadata" | "tree" | "contents" | "analyze";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  status?: number;
}

export type StreamEvent =
  | { type: "progress"; stage: ProgressStage; message: string }
  | { type: "result"; report: AnalysisReport }
  | { type: "error"; error: ApiErrorBody };
