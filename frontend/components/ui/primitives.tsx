import type { ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={cx("rounded-lg border border-border bg-surface", className)}
      aria-labelledby={id && title ? `${id}-title` : undefined}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-border px-4 py-3">
          <div className="min-w-0">
            {title && (
              <h2 id={id ? `${id}-title` : undefined} className="text-sm font-semibold">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums">{value}</dd>
      {hint && <dd className="truncate text-xs text-muted">{hint}</dd>}
    </div>
  );
}

type Tone = "neutral" | "good" | "warn" | "bad" | "info" | "accent";
const TONES: Record<Tone, string> = {
  neutral: "border-border text-muted",
  good: "border-good/30 bg-good/10 text-good",
  warn: "border-warn/30 bg-warn/10 text-warn",
  bad: "border-bad/30 bg-bad/10 text-bad",
  info: "border-info/30 bg-info/10 text-info",
  accent: "border-accent/30 bg-accent-soft text-accent",
};

export function Badge({ tone = "neutral", children, title }: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted">{children}</p>;
}
