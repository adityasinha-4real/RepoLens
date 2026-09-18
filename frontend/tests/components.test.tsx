import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalysisView } from "@/components/analysis/analysis-view";
import { RepoInput } from "@/components/repo-input";
import { AnalysisError, type streamAnalysis } from "@/lib/analyze-stream";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => push.mockReset());

describe("RepoInput", () => {
  it("shows a validation error and does not navigate for invalid input", async () => {
    render(<RepoInput />);
    await userEvent.type(screen.getByLabelText("GitHub repository URL"), "https://gitlab.com/a/b");
    await userEvent.click(screen.getByRole("button", { name: /analyze/i }));
    expect(screen.getByRole("alert")).toHaveTextContent("Only github.com repositories");
    expect(screen.getByLabelText("GitHub repository URL")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
  });

  it("navigates to the analysis page for a valid URL", async () => {
    render(<RepoInput />);
    await userEvent.type(
      screen.getByLabelText("GitHub repository URL"),
      "https://github.com/pallets/flask{enter}",
    );
    expect(push).toHaveBeenCalledWith("/analyze/pallets/flask");
  });

  it("clears the error when the user edits the input", async () => {
    render(<RepoInput />);
    await userEvent.click(screen.getByRole("button", { name: /analyze/i }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("GitHub repository URL"), "a");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("AnalysisView", () => {
  it("shows the current stage while loading", async () => {
    const run = vi.fn((_url, opts) => {
      opts?.onProgress?.("tree", "Fetching repository tree");
      return new Promise(() => {}); // never resolves
    }) as unknown as typeof streamAnalysis;
    render(<AnalysisView owner="o" name="r" run={run} />);
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("o/r");
    await waitFor(() => expect(status).toHaveTextContent("Fetching repository tree"));
    expect(screen.getByText("Fetch file tree").parentElement).toHaveTextContent("(in progress)");
    expect(screen.getByText("Fetch repository metadata").parentElement).toHaveTextContent("(done)");
  });

  it("shows a rate-limit error with the reset time and allows retry", async () => {
    const run = vi
      .fn()
      .mockRejectedValueOnce(
        new AnalysisError(
          { code: "rate_limited", message: "GitHub API rate limit exceeded.", details: { reset_at: "2030-03-17T17:46:40+00:00" } },
          429,
        ),
      )
      .mockReturnValueOnce(new Promise(() => {}));
    render(<AnalysisView owner="o" name="r" run={run as unknown as typeof streamAnalysis} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("GitHub API rate limit reached");
    expect(alert).toHaveTextContent("Limit resets at");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(run).toHaveBeenCalledTimes(2);
  });

  it("does not offer retry for a missing repository", async () => {
    const run = vi.fn().mockRejectedValue(
      new AnalysisError({ code: "repository_not_found", message: "Not found" }, 404),
    );
    render(<AnalysisView owner="o" name="missing" run={run as unknown as typeof streamAnalysis} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Repository not found");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
