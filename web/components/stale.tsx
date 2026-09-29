import Link from "next/link";
import type { SourceHealth } from "@/lib/data";
import { sourceLabel } from "@/lib/labels";
import { lateSources } from "@/lib/staleness";

/** BRIEF §2.7: a banner when a source is stale or past its SLA (the same rule as the digest). One line; the reasons
 * open under it. */
export function StaleBanner({ sources, now }: { sources: SourceHealth[]; now: Date }) {
  const late = lateSources(sources, now);
  if (late.length === 0) return null;
  const names = late.map((s) => sourceLabel(s.source)).join(", ");
  return (
    <aside aria-label="Stale data" className="border-b border-amber-300 bg-amber-50 text-sm text-amber-950">
      <details className="mx-auto max-w-6xl px-4 py-2">
        <summary className="marker:text-amber-800">
          <strong className="font-semibold">Stale data:</strong> {late.length === 1 ? "1 source is" : `${late.length} sources are`} out
          of date ({names}). Scores that read {late.length === 1 ? "it" : "them"} may be behind.
        </summary>
        <ul className="mt-2 mb-1 grid gap-1 pl-5 sm:grid-cols-2">
          {late.map((s) => (
            <li key={s.source} className="list-disc">
              <span className="font-medium">{sourceLabel(s.source)}</span>: {s.why}
            </li>
          ))}
        </ul>
        <p className="mb-1 text-xs">
          Each source&apos;s last success and error are under <Link href="/#sources">Source health</Link> on Home.
        </p>
      </details>
    </aside>
  );
}
