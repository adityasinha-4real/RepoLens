import Link from "next/link";
import { RepoInput } from "@/components/repo-input";
import { SiteHeader } from "@/components/site-header";
import { analyzePath } from "@/lib/repo-url";

const EXAMPLES = [
  ["pallets", "flask"],
  ["expressjs", "express"],
  ["psf", "requests"],
  ["gin-gonic", "gin"],
  ["tokio-rs", "axum"],
] as const;

const CAPABILITIES: [string, string][] = [
  ["Structure", "Interactive file tree, sizes, categories, ignored and vendored directories."],
  ["Languages", "Per-language files, bytes and lines, next to GitHub's own breakdown."],
  ["Dependencies", "11 manifest formats across 7 ecosystems, with scopes, constraints and lockfiles."],
  ["Code quality", "Complexity hotspots, long files, TODO/FIXME markers, commented-out code, tooling."],
  ["Documentation", "README sections, broken relative links, community files, docstring coverage."],
  ["Security indicators", "Secret patterns, sensitive files, risky code and CI configuration. Flagged as potential."],
  ["Architecture", "Modules, frameworks, entry points and import relationships resolved from real code."],
  ["Health report", "Seven transparent dimensions built from explicit, point-based checks."],
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-16 pt-16 sm:pt-24">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">RepoLens</h1>
        <p className="mt-2 text-lg text-muted">Understand any GitHub repository in minutes.</p>

        <div className="mt-8">
          <RepoInput autoFocus />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Try:</span>
          {EXAMPLES.map(([owner, name]) => (
            <Link
              key={`${owner}/${name}`}
              href={analyzePath(owner, name)}
              className="rounded border border-border px-2 py-0.5 font-mono text-xs text-muted transition-colors hover:border-accent hover:text-accent"
            >
              {owner}/{name}
            </Link>
          ))}
        </div>

        <section aria-labelledby="capabilities" className="mt-16">
          <h2 id="capabilities" className="text-xs font-semibold uppercase tracking-wider text-muted">
            What the report covers
          </h2>
          <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
            {CAPABILITIES.map(([title, text]) => (
              <div key={title} className="border-l-2 border-border pl-3">
                <dt className="text-sm font-medium">{title}</dt>
                <dd className="mt-0.5 text-sm text-muted">{text}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-12 rounded-lg border border-border bg-subtle p-4 text-sm text-muted">
          <p>
            <span className="font-medium text-foreground">How it works.</span> RepoLens reads a
            public repository through the GitHub API: metadata, the file tree, and a bounded
            sample of relevant files. Every result comes from deterministic static analysis.
            Repository code is never cloned, installed, built or executed. An AI summary is
            optional and off unless the server operator configures a provider.
          </p>
        </section>
      </main>
    </>
  );
}
