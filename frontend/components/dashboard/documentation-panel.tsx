import type { DocumentationAnalysis } from "@/lib/api/types";
import { formatInteger } from "@/lib/format";
import { CheckIcon, XIcon } from "../ui/icons";
import { Badge, Note, Panel, Stat } from "../ui/primitives";

function Check({ ok, label, detail }: { ok: boolean; label: string; detail?: string | null }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {ok ? (
        <CheckIcon size={14} className="mt-0.5 shrink-0 text-good" aria-label="present" />
      ) : (
        <XIcon size={14} className="mt-0.5 shrink-0 text-muted" aria-label="missing" />
      )}
      <span className={ok ? "min-w-0" : "min-w-0 text-muted"}>
        {label}
        {detail && (
          <span className="block truncate font-mono text-xs text-muted" title={detail}>
            {detail}
          </span>
        )}
      </span>
    </li>
  );
}

export function DocumentationPanel({ doc }: { doc: DocumentationAnalysis }) {
  const readme = doc.readme;
  return (
    <Panel id="documentation" title="Documentation">
      <div className="grid gap-6 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0">
          {readme ? (
            <>
              <dl className="grid grid-cols-3 gap-4">
                <Stat label="README words" value={formatInteger(readme.words)} hint={`~${readme.reading_minutes} min read`} />
                <Stat label="Headings" value={readme.headings.length} />
                <Stat label="Code blocks" value={readme.code_blocks} />
                <Stat label="Links" value={readme.links} />
                <Stat label="Images" value={readme.images} hint={`${readme.badges} badges`} />
                <Stat label="Broken links" value={readme.broken_relative_links.length} hint="relative only" />
              </dl>
              <h3 className="mb-2 mt-5 text-xs font-medium text-muted">
                README sections <span className="font-normal">(detected from headings in {readme.path})</span>
              </h3>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {readme.sections.map((s) => (
                  <Check key={s.key} ok={s.present} label={s.label} />
                ))}
              </ul>
              {readme.broken_relative_links.length > 0 && (
                <div className="mt-4">
                  <h3 className="mb-1 text-xs font-medium text-muted">Relative links pointing to missing files</h3>
                  <ul className="flex flex-wrap gap-1.5">
                    {readme.broken_relative_links.map((l) => (
                      <Badge key={l} tone="warn"><span className="font-mono">{l}</span></Badge>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">No README was found (or it was too large to download).</p>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium text-muted">Project files</h3>
          <ul className="space-y-1.5">
            <Check ok={!!doc.license_spdx || !!doc.license_file} label="License"
              detail={doc.license_spdx ?? doc.license_file ?? undefined} />
            {doc.files.filter((f) => f.key !== "license").map((f) => (
              <Check key={f.key} ok={f.present} label={f.label} detail={f.path} />
            ))}
            <Check ok={!!doc.docs_directory} label="Documentation directory"
              detail={doc.docs_directory ? `${doc.docs_directory.path}/ · ${doc.docs_directory.doc_files} docs${doc.docs_directory.site_generator ? ` · ${doc.docs_directory.site_generator}` : ""}` : null} />
            <Check ok={!!doc.examples_directory} label="Examples"
              detail={doc.examples_directory ? `${doc.examples_directory.path}/ · ${doc.examples_directory.files} files` : null} />
          </ul>
          <h3 className="mb-2 mt-5 text-xs font-medium text-muted">In-code documentation</h3>
          <ul className="space-y-1 text-sm">
            <li>
              Comment density:{" "}
              <span className="tabular-nums">{doc.comment_density !== null && doc.comment_density !== undefined ? `${(doc.comment_density * 100).toFixed(1)}%` : "—"}</span>
            </li>
            {doc.python_docstrings && (
              <li>
                Python docstrings: <span className="tabular-nums">{doc.python_docstrings.percent}%</span>{" "}
                <span className="text-xs text-muted">
                  ({doc.python_docstrings.documented}/{doc.python_docstrings.public_definitions} public definitions)
                </span>
              </li>
            )}
          </ul>
          {doc.notes.length > 0 && <div className="mt-3"><Note>{doc.notes.join(" ")}</Note></div>}
        </div>
      </div>
    </Panel>
  );
}
