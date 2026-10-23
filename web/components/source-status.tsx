import { Chip } from "@/components/chip";
import type { SourceHealth } from "@/lib/data";
import { statusChip } from "@/lib/settings";
import { sourceStatus } from "@/lib/staleness";

/** A source's status (lib/staleness.ts sourceStatus) as a soft chip: "On time" in green, "Late" in amber, "Stale" or
 * "Never ran" in red, a resting fallback "Not needed" in grey. The detail ("no success for 11 days; SLA 8") is its
 * tooltip. */
export function SourceStatus({ source, all, now }: { source: SourceHealth; all: readonly SourceHealth[]; now: Date }) {
  const c = statusChip(sourceStatus(source, all, now));
  return (
    <Chip variant={c.tone} size="sm" title={c.detail ?? undefined} className="shrink-0 font-semibold">
      {c.word}
    </Chip>
  );
}
