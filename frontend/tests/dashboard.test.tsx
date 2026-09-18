import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Dashboard } from "@/components/dashboard/dashboard";
import type { AnalysisReport } from "@/lib/api/types";
// Produced by the real backend pipeline (backend/tests/generate_frontend_fixture.py).
import fixture from "./fixtures/report.json";

const report = fixture as unknown as AnalysisReport;

describe("Dashboard", () => {
  it("renders the repository header and overview from the report", () => {
    render(<Dashboard report={report} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("octo/demo");
    expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute("href", "https://github.com/octo/demo");
    const overview = screen.getByRole("region", { name: "Overview" });
    expect(within(overview).getByText("Files")).toBeInTheDocument();
    expect(within(overview).getByText(String(report.structure.total_files))).toBeInTheDocument();
  });

  it("shows every health dimension and expands checks with evidence", async () => {
    render(<Dashboard report={report} />);
    const health = screen.getByRole("region", { name: "Repository health" });
    for (const d of report.health.dimensions) {
      expect(within(health).getByRole("button", { name: new RegExp(d.label) })).toBeInTheDocument();
    }
    await userEvent.click(within(health).getByRole("button", { name: /Project structure/ }));
    expect(within(health).getByText("No committed dependency/build directories")).toBeInTheDocument();
    expect(within(health).getByText(/Committed: node_modules/)).toBeInTheDocument();
  });

  it("renders an expandable file tree with ignored directories marked", async () => {
    render(<Dashboard report={report} />);
    const tree = screen.getByRole("tree", { name: "Repository files" });
    expect(within(tree).getByText("node_modules")).toBeInTheDocument();
    expect(within(tree).getByText("ignored")).toBeInTheDocument();
    expect(within(tree).queryByText("routes.py")).not.toBeInTheDocument();
    await userEvent.click(within(tree).getByRole("button", { name: "Expand demo" }));
    await userEvent.click(within(tree).getByRole("button", { name: "Expand api" }));
    expect(within(tree).getByRole("link", { name: "routes.py" })).toHaveAttribute(
      "href",
      `https://github.com/octo/demo/blob/${report.analysis.commit_sha}/demo/api/routes.py`,
    );
  });

  it("filters dependencies by search and scope", async () => {
    render(<Dashboard report={report} />);
    const deps = screen.getByRole("region", { name: "Dependencies" });
    const table = within(deps).getByRole("table");
    expect(within(table).getByText("fastapi")).toBeInTheDocument();
    await userEvent.selectOptions(within(deps).getByLabelText("Filter by scope"), "development");
    expect(within(table).queryByText("fastapi")).not.toBeInTheDocument();
    expect(within(table).getByText("pytest")).toBeInTheDocument();
    expect(within(deps).getByText(/has not checked these dependencies against a vulnerability database/)).toBeInTheDocument();
  });

  it("shows documentation checks", () => {
    render(<Dashboard report={report} />);
    const docs = screen.getByRole("region", { name: "Documentation" });
    expect(within(docs).getByText("Installation / setup")).toBeInTheDocument();
    expect(within(docs).getByText("Contributing guide")).toBeInTheDocument();
  });
});

describe("Architecture", () => {
  it("draws resolved module relationships and shows details for a selected module", async () => {
    render(<Dashboard report={report} />);
    const arch = screen.getByRole("region", { name: "Architecture" });
    const graph = within(arch).getByRole("group", { name: "Module dependency graph" });
    const services = within(graph).getByRole("button", { name: /^demo\/services,/ });
    await userEvent.click(services);
    expect(services).toHaveAttribute("aria-pressed", "true");
    const details = within(arch).getByText("Imported by (2)").parentElement!;
    expect(within(details).getByRole("button", { name: "demo/api" })).toBeInTheDocument();
    expect(within(details).getByRole("button", { name: "tests" })).toBeInTheDocument();
    expect(within(arch).getByText("FastAPI")).toBeInTheDocument();
  });
});
