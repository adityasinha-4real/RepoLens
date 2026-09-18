export interface SectionLink {
  id: string;
  label: string;
  count?: number;
}

export function SectionNav({ sections }: { sections: SectionLink[] }) {
  return (
    <nav
      aria-label="Report sections"
      className="sticky top-12 z-10 print:hidden -mx-4 overflow-x-auto border-b border-border bg-background/95 px-4 backdrop-blur"
    >
      <ul className="flex gap-1 py-1.5 text-sm">
        {sections.map((s) => (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded px-2 py-1 text-muted hover:bg-subtle hover:text-foreground"
            >
              {s.label}
              {s.count !== undefined && s.count > 0 && (
                <span className="rounded bg-subtle px-1 text-[11px] tabular-nums">{s.count}</span>
              )}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
