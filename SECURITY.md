# Security Policy

## Reporting a vulnerability

If you find a vulnerability in RepoLens itself (for example a way to make the backend
execute repository code, leak the configured `GITHUB_TOKEN` or AI key, read local files,
or bypass request limits), please **do not open a public issue**.

Instead, use GitHub's **private vulnerability reporting** ("Security" tab → "Report a vulnerability")
on this repository. Include reproduction steps and the affected version or commit.

You can expect an acknowledgement within 7 days.

## Scope notes

- RepoLens's *security indicators* for analyzed repositories are heuristic static checks.
  A false positive or false negative in those indicators is a normal bug, not a vulnerability.
  Please file it as a regular issue.
- RepoLens never executes, installs or builds code from analyzed repositories. Any way to
  make it do so is in scope.
