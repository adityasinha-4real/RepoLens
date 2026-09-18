"use client";

import { useEffect, useRef, useState } from "react";
import type { AnalysisReport } from "@/lib/api/types";
import { downloadFile, exportReport, type ExportFormat } from "@/lib/export/render";
import { DownloadIcon } from "../ui/icons";

const OPTIONS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "markdown", label: "Markdown", hint: "For issues, wikis and PRs" },
  { format: "html", label: "HTML", hint: "Standalone, shareable page" },
  { format: "json", label: "JSON", hint: "Complete machine-readable report" },
];

export function ExportMenu({ report }: { report: AnalysisReport }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative print:hidden">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-subtle"
      >
        <DownloadIcon size={14} /> Export
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-60 rounded-md border border-border bg-surface p-1 shadow-lg">
          {OPTIONS.map((o) => (
            <button
              key={o.format}
              type="button"
              role="menuitem"
              onClick={() => {
                const file = exportReport(report, o.format);
                downloadFile(file.filename, file.mime, file.content);
                setOpen(false);
              }}
              className="block w-full rounded px-2 py-1.5 text-left hover:bg-subtle"
            >
              <span className="block text-sm">{o.label}</span>
              <span className="block text-xs text-muted">{o.hint}</span>
            </button>
          ))}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              window.print();
            }}
            className="block w-full rounded px-2 py-1.5 text-left hover:bg-subtle"
          >
            <span className="block text-sm">Print / PDF</span>
            <span className="block text-xs text-muted">Use the browser&apos;s print dialog</span>
          </button>
        </div>
      )}
    </div>
  );
}
