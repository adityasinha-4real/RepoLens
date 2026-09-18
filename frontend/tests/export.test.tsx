import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ExportMenu } from "@/components/dashboard/export-menu";
import type { AnalysisReport } from "@/lib/api/types";
import { buildExportDocument } from "@/lib/export/document";
import { escapeMarkdown, exportReport, renderHtml, renderMarkdown } from "@/lib/export/render";
import fixture from "./fixtures/report.json";

const base = fixture as unknown as AnalysisReport;
const hostile: AnalysisReport = {
  ...base,
  repository: { ...base.repository, description: '<img src=x onerror="alert(1)"> | **bold** [x](javascript:alert(1))' },
};

describe("exports", () => {
  it("builds markdown with every report section", () => {
    const md = renderMarkdown(buildExportDocument(base));
    for (const heading of ["## Health indicators", "## Structure", "## Languages", "## Dependencies",
      "## Code quality", "## Documentation", "## Security indicators", "## Architecture"]) {
      expect(md).toContain(heading);
    }
    expect(md).toContain("| fastapi |");
    expect(md).toContain("not confirmed vulnerabilities");
    expect(md).toContain("has not checked these dependencies against a vulnerability database");
  });

  it("escapes repository content in markdown", () => {
    const md = renderMarkdown(buildExportDocument(hostile));
    const backslash = String.fromCharCode(92);
    expect(md.split(`${backslash}<img`).join("")).not.toContain("<img"); // only escaped forms
    expect(md).toContain(`${backslash}<img`);
    expect(md).toContain(`${backslash}| ${backslash}*${backslash}*bold`);
    expect(escapeMarkdown("a\nb")).toBe("a b");
  });

  it("escapes repository content in HTML and forbids scripts", () => {
    const html = renderHtml(buildExportDocument(hostile));
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
    expect(html).toContain("default-src 'none'");
    expect(html).not.toMatch(/<script/i);
  });

  it("exports the complete JSON report with a descriptive filename", () => {
    const file = exportReport(base, "json");
    expect(file.filename).toBe(`repolens-octo-demo-${base.analysis.commit_sha.slice(0, 7)}.json`);
    expect(JSON.parse(file.content)).toEqual(base);
  });

  it("downloads the chosen format from the menu", async () => {
    const createObjectURL = vi.fn(() => "blob:test");
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ExportMenu report={base} />);
    await userEvent.click(screen.getByRole("button", { name: /Export/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: /Markdown/ }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
