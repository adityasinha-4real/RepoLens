import { cx } from "../ui/primitives";

export interface Segment {
  key: string;
  label: string;
  value: number;
  color: string;
}

/** Single horizontal bar split into proportional segments, with an accessible legend. */
export function StackedBar({
  segments,
  label,
  format = (v) => String(v),
  maxLegend = 8,
}: {
  segments: Segment[];
  label: string;
  format?: (value: number) => string;
  maxLegend?: number;
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return null;
  const shown = segments.slice(0, maxLegend);
  const rest = segments.slice(maxLegend).reduce((sum, s) => sum + s.value, 0);
  return (
    <figure>
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-subtle"
        role="img"
        aria-label={`${label}: ${segments
          .map((s) => `${s.label} ${((100 * s.value) / total).toFixed(1)}%`)
          .join(", ")}`}
      >
        {segments.map((s) => (
          <span
            key={s.key}
            className="h-full"
            style={{ width: `${(100 * s.value) / total}%`, background: s.color }}
            title={`${s.label}: ${format(s.value)} (${((100 * s.value) / total).toFixed(1)}%)`}
          />
        ))}
      </div>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {shown.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ background: s.color }} />
            <span className="font-medium">{s.label}</span>
            <span className="text-muted tabular-nums">{((100 * s.value) / total).toFixed(1)}%</span>
          </span>
        ))}
        {rest > 0 && (
          <span className="text-muted">Other {((100 * rest) / total).toFixed(1)}%</span>
        )}
      </figcaption>
    </figure>
  );
}

/** Label / bar / value rows; bars are relative to the largest value. */
export function BarList({
  items,
  format = (v) => String(v),
  className,
}: {
  items: { key: string; label: React.ReactNode; value: number; hint?: React.ReactNode; color?: string }[];
  format?: (value: number) => string;
  className?: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className={cx("space-y-1.5", className)}>
      {items.map((item) => (
        <li key={item.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 text-sm">
          <div className="relative min-w-0 overflow-hidden rounded px-2 py-1">
            <span
              className="absolute inset-y-0 left-0 rounded"
              style={{
                width: `${Math.max(1.5, (100 * item.value) / max)}%`,
                background: item.color ?? "var(--accent-soft)",
                opacity: item.color ? 0.25 : 1,
              }}
              aria-hidden="true"
            />
            <span className="relative block truncate">{item.label}</span>
          </div>
          <span className="text-right text-xs tabular-nums text-muted">
            {format(item.value)}
            {item.hint && <span className="ml-1">{item.hint}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 0-100 score meter with a tone derived from the value. */
export function ScoreBar({ score, label }: { score: number | null; label: string }) {
  const tone = score === null ? "var(--border)" : score >= 80 ? "var(--good)" : score >= 50 ? "var(--warn)" : "var(--bad)";
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-subtle"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score ?? undefined}
    >
      <div className="h-full rounded-full" style={{ width: `${score ?? 0}%`, background: tone }} />
    </div>
  );
}
