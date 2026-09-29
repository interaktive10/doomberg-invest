import { Badge } from "@/components/ui/badge";
import type { SourceHealth } from "@/lib/data";
import { sourceStatus } from "@/lib/staleness";

/** A source's status (lib/staleness.ts sourceStatus) as a short badge with its detail next to it ("late" · "no success
 * for 11 days; SLA 8"): green when on time, amber when late, grey for a resting fallback, red when stale or never
 * succeeded. */
export function SourceStatus({ source, all, now }: { source: SourceHealth; all: readonly SourceHealth[]; now: Date }) {
  const text = sourceStatus(source, all, now);
  const m = /^([^(]+?)\s*\((.*)\)$/.exec(text);
  const head = m?.[1] ?? text;
  const detail = m?.[2];
  const variant = text === "ok" ? "success" : text.startsWith("fallback") ? "secondary" : text.startsWith("late") ? "warning" : "destructive";
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <Badge variant={variant}>{head}</Badge>
      {detail ? <span className="text-xs whitespace-nowrap text-gray-700">{detail}</span> : null}
    </span>
  );
}
