import type { Tone } from "@/lib/palette";
import { meterPct, splitWidths } from "@/lib/visual";
import { cn } from "@/lib/utils";

// Fill classes per tone, spelled out so Tailwind sees them.
const FILL: Record<Tone, string> = {
  business: "bg-fam-business",
  insiders: "bg-fam-insiders",
  ownership: "bg-fam-ownership",
  text: "bg-fam-text",
  evidence: "bg-accent",
  gap: "bg-gap",
  up: "bg-up",
  down: "bg-down",
  warn: "bg-warn",
  muted: "bg-subtle",
};

const HEIGHT = { sm: "h-1.5", md: "h-2", lg: "h-3.5" } as const;

/** A thin bar filled to value / max (a signal's strength, a funnel step, an insider's share of the buying). With a
 * `label` it is a meter ("Insider buying 0.89 of 1"); without one it is decoration beside a number the page prints. */
export function Meter({
  value,
  max = 100,
  tone = "evidence",
  size = "sm",
  label,
  className,
}: {
  value: number;
  max?: number;
  tone?: Tone;
  size?: keyof typeof HEIGHT;
  label?: string;
  className?: string;
}) {
  const pct = meterPct(value, max);
  const a11y = label
    ? { role: "meter", "aria-label": label, "aria-valuemin": 0, "aria-valuemax": max, "aria-valuenow": Number.isFinite(value) ? value : 0 }
    : { "aria-hidden": true };
  return (
    <div {...a11y} className={cn("w-full overflow-hidden rounded-full bg-track", HEIGHT[size], className)}>
      <div className={cn("grow-x h-full rounded-full", FILL[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** One bar split into coloured parts that add up against `max` (Evidence 94 = business 50 + insiders 44), read as one
 * image: "Business 50, insiders 44 of 100". */
export function SplitBar({
  parts,
  max = 100,
  label,
  size = "lg",
  className,
}: {
  parts: readonly { value: number; tone: Tone; label: string }[];
  max?: number;
  label?: string;
  size?: keyof typeof HEIGHT;
  className?: string;
}) {
  const widths = splitWidths(
    parts.map((p) => p.value),
    max,
  );
  const said = label ?? `${parts.map((p) => `${p.label} ${Math.round(p.value)}`).join(", ")} of ${max}`;
  return (
    <div role="img" aria-label={said} className={cn("flex w-full gap-0.5 overflow-hidden rounded-full bg-track", HEIGHT[size], className)}>
      {parts.map((p, i) => (widths[i]! > 0 ? <div key={i} className={cn("grow-x h-full", FILL[p.tone])} style={{ width: `${widths[i]}%` }} /> : null))}
    </div>
  );
}
