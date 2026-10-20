import Link from "next/link";
import type { SourceHealth } from "@/lib/data";
import { sourceLabel } from "@/lib/labels";
import { lateSources } from "@/lib/staleness";

/** BRIEF §2.7: Home's banner when a source the pipeline reads (sec, twelvedata, sec_13f) is stale or past its SLA (the
 * digest's rule). One line; the reasons open under it. Text is fg, warn or muted on the warn tint (>= 7.9:1). */
export function StaleBanner({ sources, now }: { sources: SourceHealth[]; now: Date }) {
  const late = lateSources(sources, now);
  if (late.length === 0) return null;
  const names = late.map((s) => sourceLabel(s.source)).join(", ");
  return (
    <aside aria-label="Stale data" className="border-b border-warn/30 bg-warn/10 text-[13px] text-fg">
      <details className="mx-auto max-w-[1440px] px-4 py-1.5 sm:px-6">
        <summary className="marker:text-warn">
          <strong className="font-semibold text-warn">Stale data:</strong> {late.length === 1 ? "1 source is" : `${late.length} sources are`} out
          of date ({names}). Scores that read {late.length === 1 ? "it" : "them"} may be behind.
        </summary>
        <ul className="mt-2 mb-1 grid grid-cols-1 gap-1 pl-5 text-muted sm:grid-cols-2">
          {late.map((s) => (
            <li key={s.source} className="list-disc">
              <span className="font-medium text-fg">{sourceLabel(s.source)}</span>: {s.why}
            </li>
          ))}
        </ul>
        <p className="mb-1 text-xs">
          Each source&apos;s last success and error are under <Link href="/settings#sources">Sources</Link> in Settings.
        </p>
      </details>
    </aside>
  );
}
