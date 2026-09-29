import { Badge } from "@/components/ui/badge";
import type { SourceHealth } from "@/lib/data";
import { sourceStatus } from "@/lib/staleness";

/** A source's status (lib/staleness.ts sourceStatus) as a badge: green when on time, amber when late or resting,
 * red when stale or never succeeded. */
export function SourceStatus({ source, all, now }: { source: SourceHealth; all: readonly SourceHealth[]; now: Date }) {
  const text = sourceStatus(source, all, now);
  const variant = text === "ok" ? "success" : text.startsWith("fallback") ? "secondary" : text.startsWith("late") ? "warning" : "destructive";
  return (
    <Badge variant={variant} className="whitespace-normal">
      {text}
    </Badge>
  );
}
