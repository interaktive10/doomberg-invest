import Link from "next/link";
import { Dot } from "@/components/chip";
import type { FactRow } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { big, num } from "@/lib/format";
import { humanize, unitLabel } from "@/lib/labels";

/** A verified fact's value with its unit: "13.20B USD", "18.0%", "2–3 years". */
export function factValue(f: Pick<FactRow, "value_num" | "value_low" | "value_high" | "unit">): string {
  const pct = f.unit === "percent";
  const v = (x: number | null) => (x === null ? "n/a" : pct ? `${num(x)}%` : big(x));
  const base =
    f.value_num !== null ? v(f.value_num) : f.value_low !== null || f.value_high !== null ? `${v(f.value_low)}–${v(f.value_high)}` : "";
  return pct || base === "" ? base : `${base} ${unitLabel(f.unit)}`;
}

/** A verified text fact as a compact quote (BRIEF §2.5): the exact words it was checked against, then what it says, when,
 * and the document. The anchor #fact-<id> is where a card's [f:<id>] citation points (components/open-target.tsx opens
 * the folded list around it); the stored subject key is the kind's title. */
export function FactItem({ f, company }: { f: FactRow & { company_id: string }; company?: boolean }) {
  const value = factValue(f);
  return (
    <li id={`fact-${f.id}`} className="tile scroll-mt-24 p-3.5 target:ring-2 target:ring-accent/40 md:p-4">
      <blockquote className="text-[14px] leading-relaxed text-fg">“{f.quote}”</blockquote>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-subtle">
        {company && f.companies ? (
          <Link href={`/company/${f.company_id}`} className="link-quiet text-[12px]">
            {f.companies.name}
          </Link>
        ) : null}
        <span className="inline-flex items-center gap-1.5 font-semibold text-muted" title={f.subject_key}>
          <Dot tone="text" />
          {humanize(f.fact_type)}
          {value ? <span className="num">{value}</span> : null}
        </span>
        <span className="num">
          {f.period_label ? `${f.period_label} · ` : ""}as of {shortDate(f.as_of, true)}
        </span>
        {f.documents ? (
          <a href={f.documents.url} rel="noreferrer" target="_blank" title={f.documents.title ?? undefined} className="text-[12px]">
            {f.documents.kind}, {shortDate(f.documents.published_at, true)}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : null}
      </div>
    </li>
  );
}
