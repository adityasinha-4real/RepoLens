import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AnalysisView } from "@/components/analysis/analysis-view";
import { RepoInput } from "@/components/repo-input";
import { SiteHeader } from "@/components/site-header";
import { parseRepoInput } from "@/lib/repo-url";

export async function generateMetadata(props: PageProps<"/analyze/[owner]/[repo]">): Promise<Metadata> {
  const { owner, repo } = await props.params;
  return { title: `${decodeURIComponent(owner)}/${decodeURIComponent(repo)}` };
}

export default async function AnalyzePage(props: PageProps<"/analyze/[owner]/[repo]">) {
  const { owner, repo } = await props.params;
  const parsed = parseRepoInput(`${decodeURIComponent(owner)}/${decodeURIComponent(repo)}`);
  if (!parsed.ok) notFound();

  return (
    <>
      <SiteHeader>
        <div className="hidden max-w-md md:block">
          <RepoInput compact initialValue={`${parsed.owner}/${parsed.name}`} />
        </div>
      </SiteHeader>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-16 pt-6">
        {/* key forces a fresh analysis when navigating between repositories */}
        <AnalysisView key={`${parsed.owner}/${parsed.name}`} owner={parsed.owner} name={parsed.name} />
      </main>
    </>
  );
}
