import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { QualityPanel } from "@/components/dashboard/quality-panel";
import { SecurityPanel } from "@/components/dashboard/security-panel";
import type { AnalysisReport, SecurityFinding } from "@/lib/api/types";
import fixture from "./fixtures/report.json";

const base = fixture as unknown as AnalysisReport;

function withFindings(extra: SecurityFinding[]): AnalysisReport {
  const findings = [...extra, ...base.security.findings];
  const counts: Record<string, number> = { high: 0, medium: 0, low: 0, info: 0 };
  for (const f of findings) counts[f.severity] += 1;
  return { ...base, security: { ...base.security, findings, counts_by_severity: counts } };
}

describe("QualityPanel", () => {
  it("links markers to the exact line at the analyzed commit", () => {
    render(<QualityPanel report={base} />);
    const link = screen.getByRole("link", { name: "demo/api/routes.py:5" });
    expect(link).toHaveAttribute("href", `https://github.com/octo/demo/blob/${base.analysis.commit_sha}/demo/api/routes.py#L5`);
    expect(screen.getByText("TODO: paginate")).toBeInTheDocument();
    expect(screen.getByText(base.quality.coverage_note)).toBeInTheDocument();
  });

  it("filters markers by tag", async () => {
    render(<QualityPanel report={base} />);
    await userEvent.click(screen.getByRole("button", { name: "FIXME 0" }));
    expect(screen.queryByText("TODO: paginate")).not.toBeInTheDocument();
    expect(screen.getByText("No markers found in the downloaded files.")).toBeInTheDocument();
  });
});

describe("SecurityPanel", () => {
  const report = withFindings([
    {
      rule: "secret.github-token", title: "Possible GitHub token", severity: "high", confidence: "high",
      category: "secret", path: "src/config.py", line: 3, evidence: 'TOKEN = "ghp_********(40 chars)"',
      description: "Matches the GitHub token format.", in_test: false,
    },
    {
      rule: "file.sensitive", title: "Environment file committed", severity: "medium", confidence: "medium",
      category: "sensitive-file", path: "tests/fixtures/.env", line: null, evidence: null,
      description: "A .env file often contains real credentials.", in_test: true,
    },
  ]);

  it("always shows the disclaimer and never claims the repository is secure", () => {
    render(<SecurityPanel report={report} />);
    expect(screen.getByRole("note")).toHaveTextContent("not confirmed vulnerabilities");
    expect(screen.getByRole("note")).toHaveTextContent("does not mean the repository is secure");
  });

  it("hides test/example findings by default and filters by severity", async () => {
    render(<SecurityPanel report={report} />);
    const list = () => screen.getByRole("list", { name: "Findings" });
    expect(within(list()).getByText("Possible GitHub token")).toBeInTheDocument();
    expect(within(list()).getByText('TOKEN = "ghp_********(40 chars)"')).toBeInTheDocument();
    expect(within(list()).queryByText("Environment file committed")).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/Include 1 finding/));
    expect(within(list()).getByText("Environment file committed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^low/i }));
    expect(within(list()).getByText("Container base image without a pinned version")).toBeInTheDocument();
    expect(within(list()).queryByText("Possible GitHub token")).not.toBeInTheDocument();
  });

  it("states that an empty result does not mean the repository is secure", () => {
    render(<SecurityPanel report={{ ...base, security: { ...base.security, findings: [] } }} />);
    expect(screen.queryByRole("list", { name: "Findings" })).not.toBeInTheDocument();
    expect(screen.getByText(/No potential concerns were detected by these rules/)).toHaveTextContent(
      "That does not mean the repository is secure.",
    );
  });
});
