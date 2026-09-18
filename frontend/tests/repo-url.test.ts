import { describe, expect, it } from "vitest";
import { analyzePath, parseRepoInput } from "@/lib/repo-url";

describe("parseRepoInput", () => {
  it.each([
    ["https://github.com/facebook/react", "facebook", "react"],
    ["http://www.github.com/facebook/react.git", "facebook", "react"],
    ["github.com/vercel/next.js/tree/canary/packages", "vercel", "next.js"],
    ["  psf/requests  ", "psf", "requests"],
    ["git@github.com:rust-lang/rust.git", "rust-lang", "rust"],
    ["https://github.com/psf/requests?tab=readme#install", "psf", "requests"],
  ])("accepts %s", (input, owner, name) => {
    expect(parseRepoInput(input)).toEqual({ ok: true, owner, name });
  });

  it.each([
    ["", "Enter a GitHub repository URL."],
    ["https://github.com/facebook", "Use a repository URL"],
    ["https://gitlab.com/group/project", "Only github.com"],
    ["https://github.com.evil.com/a/b", "Only github.com"],
    ["ftp://github.com/a/b", "Only http(s)"],
    ["https://user:pw@github.com/a/b", "credentials"],
    ["https://github.com/-bad/repo", "not a valid GitHub owner"],
    ["https://github.com/settings/profile", "not a valid GitHub owner"],
    ["owner/..", "not a valid repository name"],
    ["owner/repo name", "whitespace"],
    ["a".repeat(600), "too long"],
  ])("rejects %s", (input, message) => {
    const result = parseRepoInput(input);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain(message);
  });

  it("builds encoded analysis paths", () => {
    expect(analyzePath("vercel", "next.js")).toBe("/analyze/vercel/next.js");
  });
});
