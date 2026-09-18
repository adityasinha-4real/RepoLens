// A tiny document model for exports: build once from the report, render to Markdown or HTML.
import type { AnalysisReport } from "../api/types";
import { formatBytes, formatInteger } from "../format";

export type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; headers: string[]; rows: string[][]; align?: ("left" | "right")[] }
  | { kind: "note"; text: string };

export interface ExportDocument {
  title: string;
  subtitle: string;
  blocks: Block[];
}

const yes = (v: boolean) => (v ? "yes" : "no");

export function buildExportDocument(report: AnalysisReport): ExportDocument {
  const r = report.repository;
  const a = report.analysis;
  const s = report.structure;
  const l = report.languages;
  const d = report.dependencies;
  const q = report.quality;
  const doc = report.documentation;
  const sec = report.security;
  const arch = report.architecture;
  const b: Block[] = [];

  b.push({ kind: "paragraph", text: r.description ?? "No description." });
  b.push({
    kind: "table",
    headers: ["Field", "Value"],
    rows: [
      ["Repository", r.html_url],
      ["Commit", a.commit_sha],
      ["Analyzed at", a.analyzed_at],
      ["Stars / forks / open issues+PRs", `${formatInteger(r.stars)} / ${formatInteger(r.forks)} / ${formatInteger(r.open_issues)}`],
      ["Primary language", r.primary_language ?? "—"],
      ["License", r.license_spdx ?? "—"],
      ["Last push", r.pushed_at ?? "—"],
      ["Archived", yes(r.archived)],
      ["Partial analysis", yes(a.partial)],
    ],
  });
  if (a.notes.length) b.push({ kind: "list", items: a.notes });

  b.push({ kind: "heading", level: 2, text: "Health indicators" });
  b.push({ kind: "paragraph", text: `Overall: ${report.health.overall ?? "n/a"} (unweighted mean of applicable dimensions).` });
  b.push({
    kind: "table",
    headers: ["Dimension", "Score", "Summary"],
    align: ["left", "right", "left"],
    rows: report.health.dimensions.map((dim) => [dim.label, dim.applicable ? String(dim.score) : "n/a", dim.summary]),
  });
  for (const dim of report.health.dimensions) {
    b.push({ kind: "heading", level: 3, text: dim.label });
    b.push({
      kind: "table",
      headers: ["Check", "Result", "Points", "Evidence"],
      rows: dim.checks.map((c) => [c.label, c.passed ? "pass" : "fail", `${c.points}/${c.max_points}`, c.detail]),
    });
  }
  b.push({ kind: "note", text: report.health.methodology });

  b.push({ kind: "heading", level: 2, text: "Structure" });
  b.push({
    kind: "list",
    items: [
      `${formatInteger(s.total_files)} files (${formatInteger(s.analyzed_files)} analyzed, ${formatInteger(s.ignored_files)} in ignored directories)`,
      `${formatInteger(s.total_directories)} directories, max depth ${s.max_depth}`,
      `Size: ${formatBytes(s.total_size_bytes)}`,
      `Categories: ${s.categories.map((c) => `${c.category} ${c.files}`).join(", ")}`,
    ],
  });
  if (s.ignored_directories.length) {
    b.push({ kind: "paragraph", text: `Ignored directories: ${s.ignored_directories.map((i) => `${i.path}/ (${i.files} files)`).join(", ")}` });
  }

  b.push({ kind: "heading", level: 2, text: "Languages" });
  b.push({
    kind: "table",
    headers: ["Language", "Files", "Lines", "Share of bytes"],
    align: ["left", "right", "right", "right"],
    rows: l.languages.slice(0, 20).map((x) => [x.language, formatInteger(x.files), `${x.lines_estimated ? "≈" : ""}${formatInteger(x.lines)}`, `${x.percent_of_bytes}%`]),
  });
  b.push({ kind: "note", text: l.methodology });

  b.push({ kind: "heading", level: 2, text: "Dependencies" });
  b.push({
    kind: "paragraph",
    text: `${formatInteger(d.total)} declarations (${formatInteger(d.production)} production, ${formatInteger(d.development)} development) across ${d.manifests.length} manifest(s). ${formatInteger(d.unconstrained)} without a version constraint.`,
  });
  if (d.ecosystems.length) {
    b.push({
      kind: "table",
      headers: ["Ecosystem", "Dependencies", "Lockfile"],
      rows: d.ecosystems.map((e) => [e.ecosystem, formatInteger(e.dependencies), yes(e.has_lockfile)]),
    });
  }
  if (d.dependencies.length) {
    b.push({
      kind: "table",
      headers: ["Package", "Version", "Scope", "Ecosystem", "Manifest"],
      rows: d.dependencies.slice(0, 300).map((x) => [x.name, x.version ?? "—", x.scope, x.ecosystem, x.manifest]),
    });
  }
  b.push({ kind: "note", text: d.vulnerability_data });

  b.push({ kind: "heading", level: 2, text: "Code quality" });
  b.push({
    kind: "list",
    items: [
      `${formatInteger(q.source_files)} source files, ${formatInteger(q.test_files)} test files`,
      `CI: ${q.tooling.ci.join(", ") || "none"}; linters: ${q.tooling.linters.join(", ") || "none"}; formatters: ${q.tooling.formatters.join(", ") || "none"}; type checking: ${q.tooling.type_checkers.join(", ") || "none"}; tests: ${q.tooling.test_frameworks.join(", ") || "none"}`,
      `Markers: ${Object.entries(q.marker_counts).map(([k, v]) => `${k} ${v}`).join(", ")}`,
      `${formatInteger(q.long_file_count)} files over ${q.long_file_threshold} lines; ${formatInteger(q.high_complexity_count)} complexity hotspots`,
    ],
  });
  if (q.complexity_hotspots.length) {
    b.push({
      kind: "table",
      headers: ["Location", "Complexity", "Method"],
      rows: q.complexity_hotspots.slice(0, 20).map((c) => [c.name ? `${c.path}:${c.line} ${c.name}` : c.path, String(c.complexity), c.method]),
    });
  }
  b.push({ kind: "note", text: q.coverage_note });

  b.push({ kind: "heading", level: 2, text: "Documentation" });
  b.push({
    kind: "list",
    items: [
      doc.readme ? `README: ${doc.readme.path}, ${formatInteger(doc.readme.words)} words, ${doc.readme.broken_relative_links.length} broken relative link(s)` : "No README found",
      ...doc.files.map((f) => `${f.label}: ${f.present ? f.path : "missing"}`),
    ],
  });

  b.push({ kind: "heading", level: 2, text: "Security indicators" });
  b.push({ kind: "note", text: sec.disclaimer });
  const findings = sec.findings.filter((f) => !f.in_test);
  if (findings.length) {
    b.push({
      kind: "table",
      headers: ["Severity", "Indicator", "Location", "Evidence (redacted)"],
      rows: findings.slice(0, 100).map((f) => [f.severity, f.title, `${f.path}${f.line ? `:${f.line}` : ""}`, f.evidence ?? ""]),
    });
  } else {
    b.push({ kind: "paragraph", text: "No indicators outside tests and examples. This does not mean the repository is secure." });
  }
  b.push({ kind: "list", items: sec.hygiene.map((h) => `${h.label}: ${h.passed ? "yes" : "no"} (${h.detail})`) });

  b.push({ kind: "heading", level: 2, text: "Architecture" });
  b.push({
    kind: "list",
    items: [
      `Project types: ${arch.project_types.map((t) => t.name).join(", ") || "not determined"}`,
      `Frameworks: ${arch.frameworks.map((f) => f.name).join(", ") || "none detected"}`,
      `Entry points: ${arch.entry_points.map((e) => e.path).join(", ") || "none identified"}`,
    ],
  });
  if (arch.edges.length) {
    b.push({
      kind: "table",
      headers: ["From module", "To module", "Resolved imports"],
      rows: arch.edges.slice(0, 60).map((e) => [e.source, e.target, String(e.imports)]),
    });
  }
  b.push({ kind: "note", text: arch.methodology });

  return {
    title: `RepoLens report: ${r.full_name}`,
    subtitle: `Commit ${a.commit_sha.slice(0, 12)} · analyzed ${a.analyzed_at} · RepoLens ${a.engine_version}`,
    blocks: b,
  };
}
