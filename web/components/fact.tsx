import Link from "next/link";
import type { FactRow } from "@/lib/data";
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

/** A verified text fact: what it says, the exact quote it was checked against, and the document (BRIEF §2.5). The
 * anchor #fact-<id> is where a card's [f:<id>] citation points. */
export function FactItem({ f, company }: { f: FactRow & { company_id: string }; company?: boolean }) {
  const value = factValue(f);
  return (
    <li id={`fact-${f.id}`} className="scroll-mt-4 rounded-lg border border-gray-200 bg-white p-3 target:border-blue-700 target:ring-2 target:ring-blue-700/20">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
        {company && f.companies ? (
          <Link href={`/company/${f.company_id}`} className="link-quiet">
            {f.companies.name}
          </Link>
        ) : null}
        <span className="font-semibold text-gray-900">{humanize(f.fact_type)}</span>
        {value ? <span className="font-medium text-gray-900 tabular-nums">{value}</span> : null}
        <span className="text-gray-700">
          {f.period_label ? `${f.period_label} · ` : ""}as of {f.as_of}
        </span>
        <code className="ml-auto text-xs break-all text-gray-700">{f.subject_key}</code>
      </div>
      <blockquote className="mt-2 border-l-2 border-gray-300 pl-3 text-sm text-gray-900">“{f.quote}”</blockquote>
      {f.documents ? (
        <a href={f.documents.url} rel="noreferrer" target="_blank" className="mt-2 inline-block text-xs">
          {f.documents.kind} {f.documents.published_at.slice(0, 10)}
          {f.documents.title ? `: ${f.documents.title}` : ""}
          <span className="sr-only"> (opens in a new tab)</span> ↗
        </a>
      ) : null}
    </li>
  );
}
