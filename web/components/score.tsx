import { Badge } from "@/components/ui/badge";
import { num } from "@/lib/format";
import { FAMILY_LABEL, label, RED_FLAG_NAME, SIGNAL_NAME } from "@/lib/labels";

/** A 0–100 score as its number and a small bar (the bar is decoration; the number is the value). */
export function ScoreBar({ value, digits = 1 }: { value: number | string | null | undefined; digits?: number }) {
  const n = value === null || value === undefined || value === "" ? null : Number(value);
  const width = n === null || !Number.isFinite(n) ? 0 : Math.max(0, Math.min(100, n));
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="num">{num(value, digits)}</span>
      <span aria-hidden="true" className="hidden h-1 w-14 overflow-hidden bg-line-strong sm:inline-block">
        <span className="block h-full bg-accent" style={{ width: `${width}%` }} />
      </span>
    </span>
  );
}

/** Signal ids (S1…S12) as badges, each titled with its name (BRIEF §1.4). */
export function SignalBadges({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((s) => (
        <Badge key={s} title={SIGNAL_NAME[s] ?? s}>
          {s}
        </Badge>
      ))}
    </span>
  );
}

/** Red-flag ids (R1…R6) as badges titled with their rule (BRIEF §1.5); red when a hard flag fired, amber otherwise. */
export function FlagBadges({ ids, hard }: { ids: readonly string[]; hard: boolean }) {
  if (ids.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((f) => (
        <Badge key={f} variant={hard ? "destructive" : "warning"} title={RED_FLAG_NAME[f] ?? f}>
          {f}
        </Badge>
      ))}
    </span>
  );
}

export function FamilyBadges({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((f) => (
        <Badge key={f} variant="secondary">
          {label(FAMILY_LABEL, f)}
        </Badge>
      ))}
    </span>
  );
}
