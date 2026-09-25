import type { SourceHealth } from "@/lib/data";
import { staleSources } from "@/lib/staleness";

/** BRIEF §2.7: a banner when a source is stale or past its SLA (the same rule as the digest). */
export function StaleBanner({ sources, now }: { sources: SourceHealth[]; now: Date }) {
  const late = staleSources(sources, now);
  if (late.length === 0) return null;
  return (
    <div role="alert" className="border-b border-amber-700 bg-amber-50 px-4 py-2 text-sm text-gray-900">
      <strong>Stale data:</strong> {late.join(", ")}. Signals and scores that read these sources may be out of date.
    </div>
  );
}
