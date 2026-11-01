import Link from "next/link";
import { Callout } from "@/components/callout";
import { Disclosure } from "@/components/disclosure";
import { Icon } from "@/components/icons";
import { LinkPending } from "@/components/link-pending";
import { Empty, Page, Section } from "@/components/page";
import { requireUser } from "@/lib/auth";
import { latestReport } from "@/lib/data";
import { dayDate, shortDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { evidenceLine, reviewOf, sharePct, type EarlierCall, type Review, type Theme, type ThemesReport } from "@/lib/themes";
import { marketName, signedPct } from "@/lib/winners";

export const metadata = { title: "Themes" };

// Themes (docs/SPEC_ISSUES.md 67): where demand is building before the price. The week's thinking in one line, each
// theme as a card (how broad the demand is, how far the price has moved, why, what would prove it wrong, the companies
// behind it), then the earlier calls and how they have done. Rewritten every Saturday from the week's evidence.
export default async function Themes() {
  await requireUser();
  const report = await latestReport<ThemesReport>("themes");
  const r = report?.body;
  return (
    <Page title="Themes" description="Where demand is building before the price. Rethought every Saturday.">
      {!r ? (
        <Empty>The first themes are written on Saturday, after the week&apos;s scores.</Empty>
      ) : (
        <>
          {r.note ? (
            <Callout>
              <strong className="font-semibold text-fg">This week&apos;s thinking: </strong>
              {r.note}
            </Callout>
          ) : null}
          {r.themes.length === 0 ? (
            <Empty>
              {r.answered || r.candidates === 0
                ? "No industry shows broad demand that the price hasn't caught yet."
                : "The theme pass didn't answer this week; the industry table below is up to date."}
            </Empty>
          ) : (
            <ul aria-label="This week's themes" className="grid gap-5 lg:grid-cols-2">
              {r.themes.map((t, i) => (
                <ThemeCard key={`${t.market}-${t.industry}`} t={t} median={r.medians[t.market] ?? 0} i={i} />
              ))}
            </ul>
          )}
          {r.scorecard.length > 0 ? <Earlier calls={r.scorecard} reviews={r.reviews} /> : null}
          <Disclosure summary={`All ${r.industries.length} industries`}>
            <Industries rows={r.industries} medians={r.medians} />
          </Disclosure>
          <p className="text-[13px] text-subtle">
            Demand evidence: verified order and customer wins, capacity additions, lead-time and price-increase statements
            from filings in the last six months, a growing order book, or revenue growth that sped up. Price: the median
            12-month move of the industry&apos;s companies. Research, not advice · computed {dayDate(report!.week_end)}.
          </p>
        </>
      )}
    </Page>
  );
}

const CONFIDENCE = { low: "Low confidence", medium: "Medium confidence", high: "High confidence" } as const;

function ThemeCard({ t, median, i }: { t: Theme; median: number; i: number }) {
  const ahead = t.median_move - median;
  return (
    <li className="sheet rise flex min-w-0 flex-col gap-4 p-5 md:p-6" style={{ "--i": i } as React.CSSProperties}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="eyebrow">
          {marketName(t.market)} · {t.industry}
        </span>
        <span className={cn("rounded-full px-2.5 py-0.5 text-[12px] font-semibold", t.early ? "bg-tint-sage text-up" : "bg-tint-sand text-warn")}>
          {t.early ? "Price hasn't moved" : "Price already moving"}
        </span>
      </div>
      <h2 className="text-[22px] leading-tight font-bold tracking-[-0.02em] text-fg">{t.title}</h2>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5 rounded-tile bg-raised p-3">
          <span className="text-[12px] font-medium text-muted">Demand</span>
          <span className="num text-[20px] font-bold text-fg">
            {t.with_demand}
            <span className="text-[14px] font-semibold text-subtle"> of {t.companies}</span>
          </span>
          <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-track">
            <span className="grow-x block h-full rounded-full bg-up" style={{ width: `${sharePct(t.share)}%` }} />
          </span>
        </div>
        <div className="flex flex-col gap-1.5 rounded-tile bg-raised p-3">
          <span className="text-[12px] font-medium text-muted">Price, 12 months</span>
          <span className="num text-[20px] font-bold text-fg">{signedPct(t.median_move)}</span>
          <span className={cn("text-[12px]", ahead > 0 ? "text-warn" : "text-up")}>
            {ahead > 0 ? `${signedPct(ahead)} vs market` : `${signedPct(ahead)} vs market`}
          </span>
        </div>
      </div>
      <p className="text-[15px] leading-relaxed text-fg">{t.why}</p>
      <p className="flex items-start gap-2 text-[13px] text-muted">
        <Icon name="alert" className="mt-0.5 text-warn" />
        <span>
          <span className="font-semibold text-fg">Wrong if: </span>
          {t.wrong_if}
        </span>
      </p>
      <ul aria-label={`Behind ${t.title}`} className="flex flex-col gap-1.5">
        {t.evidence.map((e) => (
          <li key={e.id}>
            <Link
              href={`/company/${e.company_id}`}
              className="press tile flex items-center gap-3 px-3 py-2 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
            >
              <span className="w-16 shrink-0 truncate text-[13px] font-bold">{e.code ?? e.name}</span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-muted">{evidenceLine(e.what)}</span>
              <span className={cn("num shrink-0 text-[12px] font-semibold", e.move >= 0 ? "text-up" : "text-down")}>{signedPct(e.move)}</span>
              <LinkPending />
            </Link>
          </li>
        ))}
      </ul>
      <p className="text-[12px] text-subtle">{CONFIDENCE[t.confidence]}</p>
    </li>
  );
}

/** The earlier calls (one per industry, newest first) with their companies' move since and this week's verdict. */
function Earlier({ calls, reviews }: { calls: EarlierCall[]; reviews: Review[] }) {
  return (
    <Section id="earlier" title="Earlier calls" description="How the companies behind each call have moved since, and whether this week's pass kept it.">
      <ul className="flex flex-col">
        {calls.map((c) => {
          const r = reviewOf(reviews, c);
          return (
            <li key={`${c.market}-${c.industry}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-3 first:border-t-0 first:pt-0">
              <span className="num w-14 shrink-0 text-[13px] text-subtle">{shortDate(c.week)}</span>
              <span className="min-w-0 flex-1 text-[15px] font-semibold text-fg">
                {c.title} <span className="text-[13px] font-normal text-muted">· {marketName(c.market === "in" ? "in" : "us")} {c.industry}</span>
              </span>
              <span className={cn("num text-[14px] font-semibold", c.since === null ? "text-subtle" : c.since >= 0 ? "text-up" : "text-down")}>
                {c.since === null ? "n/a" : signedPct(c.since)}
              </span>
              {r ? (
                <span className="w-full pl-[4.25rem] text-[13px] text-muted">
                  <span className={cn("font-semibold", r.decision === "keep" ? "text-up" : "text-warn")}>{r.decision === "keep" ? "Kept" : "Dropped"}</span>: {r.reason}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Industries({ rows, medians }: { rows: ThemesReport["industries"]; medians: ThemesReport["medians"] }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[30rem] text-[13px]">
        <thead>
          <tr className="text-left">
            <th className="caps py-2 pr-3">Industry</th>
            <th className="caps py-2 pr-3">Demand</th>
            <th className="caps py-2 text-right">Price 12m</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 30).map((r) => (
            <tr key={`${r.market}-${r.industry}`} className="border-t border-line">
              <td className="py-2 pr-3 text-fg">
                {r.industry} <span className="text-subtle">· {marketName(r.market)}</span>
              </td>
              <td className="num py-2 pr-3 text-muted">
                {r.with_demand} of {r.companies}
              </td>
              <td className={cn("num py-2 text-right", r.median_move > (medians[r.market] ?? 0) ? "text-warn" : "text-muted")}>{signedPct(r.median_move)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
