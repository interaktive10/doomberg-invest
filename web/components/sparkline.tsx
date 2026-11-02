import { cn } from "@/lib/utils";

/** A small line of a series' last values (a theme's trigger on its card): a 2 px line, the latest point marked, no
 * axes. Decoration beside words that say the same (the card's trigger reading), so hidden from screen readers; the
 * theme's page has the full chart with hover. */
export function Sparkline({ values, className }: { values: readonly number[]; className?: string }) {
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) return null;
  const w = 120;
  const h = 32;
  const pad = 4;
  const lo = Math.min(...pts);
  const hi = Math.max(...pts);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (pts.length - 1);
  const y = (v: number) => pad + (h - 2 * pad) * (1 - (v - lo) / span);
  const d = pts.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = pts.length - 1;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true" className={cn("h-8 w-full overflow-visible text-accent", className)}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {/* a zero-length round-capped stroke stays a circle when the viewBox stretches (a <circle> would turn oval) */}
      <path d={`M${x(last).toFixed(1)},${y(pts[last]!).toFixed(1)}h0`} stroke="var(--panel)" strokeWidth="12" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <path d={`M${x(last).toFixed(1)},${y(pts[last]!).toFixed(1)}h0`} stroke="currentColor" strokeWidth="8" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
