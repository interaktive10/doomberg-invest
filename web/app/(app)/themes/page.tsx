import Link from "next/link";
import { Callout } from "@/components/callout";
import { LineChartCard } from "@/components/charts";
import { Icon } from "@/components/icons";
import { CapRangeLink } from "@/components/cap-range";
import { Disclosure } from "@/components/disclosure";
import { LinkPending } from "@/components/link-pending";
import { Empty, Page, Section } from "@/components/page";
import { ThemePicker, type PickerGroup } from "@/components/theme-picker";
import { requireUser } from "@/lib/auth";
import { latestReport } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { one, type Query } from "@/lib/forms";
import { CAP_STEPS, capText, inCapRange, parseRange, type CapRange } from "@/lib/caps";
import {
  byCategory,
  historyLine,
  isLibrary,
  lagWords,
  pct,
  readingWords,
  basisLines,
  basisShort,
  zWords,
  STATUS,
  STATUS_ORDER,
  STATUS_SHORT,
  type LibraryTheme,
  type RetiredTheme,
  type Status,
  type ThemesReport,
} from "@/lib/themes";
import { cn } from "@/lib/utils";
import { marketName } from "@/lib/winners";

export const metadata = { title: "Themes" };

// Themes v2 (docs/SPEC_ISSUES.md 68): a library of chains from something measurable in the world (car sales, home
// sales, rates, power, prices, or the companies' own filings) to the companies it should lift. The dropdown opens any
// theme; with none picked, the library by status. Numbers refresh every Saturday; the library is rethought monthly.
export default async function Themes({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser();
  const q = await searchParams;
  const report = await latestReport<unknown>("themes");
  const r = report && isLibrary(report.body) ? report.body : null;
  const pick = typeof q.t === "string" ? q.t : "";
  const theme = r?.library.find((t) => t.slug === pick);
  const gone = theme ? undefined : r?.retired.find((t) => t.slug === pick);
  return (
    <Page
      title="Themes"
      description="What is happening in the world, and the companies it should lift before their price does."
      actions={r ? <ThemePicker groups={groups(r)} current={theme || gone ? pick : ""} /> : undefined}
    >
      {!r ? (
        <Empty>The first theme library is built on Saturday, after the week&apos;s scores.</Empty>
      ) : theme ? (
        <Detail t={theme} r={r} ranges={{ us: parseRange(one(q, "cap_us"), CAP_STEPS.us.length), in: parseRange(one(q, "cap_in"), CAP_STEPS.in.length) }} />
      ) : gone ? (
        <Retired t={gone} />
      ) : (
        <Overview r={r} />
      )}
      {r ? (
        <p className="text-[13px] text-subtle">
          Numbers refresh every Saturday. The AI rethinks the library once a month (sooner when a theme&apos;s status
          changes or its driver jumps): it keeps, edits or retires themes and adds new ones the numbers point to.
          {r.last_rethink ? ` Last rethink ${shortDate(r.last_rethink, true)}.` : " No rethink yet."} Next{" "}
          {shortDate(r.next_rethink, true)}. Research, not advice.
        </p>
      ) : null}
    </Page>
  );
}

function groups(r: ThemesReport): PickerGroup[] {
  const out = byCategory(r.library).map(([label, list]) => ({
    label,
    options: list.map((t) => ({ value: t.slug, label: `${t.title} · ${STATUS_SHORT[t.status]}` })),
  }));
  if (r.retired.length > 0) out.push({ label: "Retired", options: r.retired.map((t) => ({ value: t.slug, label: t.title })) });
  return out;
}

const TONE_CHIP: Record<"up" | "warn" | "muted" | "down", string> = {
  up: "bg-tint-sage text-up",
  warn: "bg-tint-sand text-warn",
  muted: "bg-hover text-muted",
  down: "bg-tint-clay text-down",
};

/** The status as a chip: the short word on a card, the full label on a theme's own page; the meaning in its title. */
function StatusChip({ s, full = false }: { s: Status; full?: boolean }) {
  return (
    <span title={STATUS[s].hint} className={cn("rounded-full px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap", TONE_CHIP[STATUS[s].tone])}>
      {full ? STATUS[s].label : STATUS_SHORT[s]}
    </span>
  );
}

/** How to read the screen, in four lines (Manzoor, 2026-11-02: "i didn't understand building, fading, etc"). */
function HowToRead() {
  return (
    <Disclosure summary="How to read this" className="sheet px-5 py-4">
      <div className="flex flex-col gap-3 pt-2 text-[14px] text-muted">
        <p>
          Each theme is a chain: <strong className="font-semibold text-fg">a trigger</strong> in the world (more cars sold, more people online, rates
          falling) reaches <strong className="font-semibold text-fg">certain companies</strong>, sometimes years later (cars bought in 2021 need tires
          around 2025). Every Saturday we check each trigger against its own past 20 years and how far its stocks have already moved.
        </p>
        <ul className="flex flex-col gap-1.5">
          {STATUS_ORDER.map((s) => (
            <li key={s} className="flex items-start gap-2">
              <StatusChip s={s} />
              <span>
                <span className="font-semibold text-fg">{STATUS[s].label}:</span> {STATUS[s].hint}.
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Disclosure>
  );
}

/** "US light vehicle sales → tire, motor vehicle parts" */
function chainLine(t: LibraryTheme, r: ThemesReport): string {
  const from = t.driver === "filings" ? "Company filings" : (r.drivers[t.driver] ?? t.driver);
  return `${from} → ${t.keywords.slice(0, 3).join(", ")}`;
}

function Overview({ r }: { r: ThemesReport }) {
  return (
    <>
      <HowToRead />
      {r.note ? (
        <Callout>
          <strong className="font-semibold text-fg">The AI&apos;s latest thinking: </strong>
          {r.note}
        </Callout>
      ) : null}
      {STATUS_ORDER.map((s) => {
        const list = r.library.filter((t) => t.status === s);
        if (list.length === 0) return null;
        return (
          <Section key={s} id={`status-${s}`} title={STATUS[s].label} count={list.length} description={`${STATUS[s].hint[0]!.toUpperCase()}${STATUS[s].hint.slice(1)}.`} plain>
            <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {list.map((t, i) => (
                <li key={t.slug}>
                  <Link
                    href={`/themes?t=${t.slug}`}
                    style={{ "--i": i } as React.CSSProperties}
                    className="sheet rise press flex h-full flex-col gap-3 p-5 text-fg no-underline transition-transform duration-150 hover:-translate-y-0.5 hover:text-fg"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="eyebrow truncate">{t.category}</span>
                      <StatusChip s={t.status} />
                    </span>
                    <span className="text-[18px] leading-snug font-bold tracking-[-0.01em]">{t.title}</span>
                    <span className="line-clamp-2 text-[13px] text-muted">{chainLine(t, r)}</span>
                    {basisShort(t) ? <span className="num text-[12px] text-subtle">{basisShort(t)}</span> : null}
                    <span className="mt-auto grid grid-cols-3 gap-2 text-[12px]">
                      <Mini label="Trigger" value={t.signal.replace(" normal", "")} />
                      <Mini label="Rising demand" value={`${t.with_demand} of ${t.companies}`} />
                      <Mini label="Price vs mkt" value={pct(t.run)} />
                    </span>
                    <LinkPending />
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        );
      })}
    </>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex min-w-0 flex-col rounded-xl bg-raised px-2.5 py-2">
      <span className="truncate text-subtle">{label}</span>
      <span className="num truncate font-semibold text-fg">{value}</span>
    </span>
  );
}

/** How many of a theme's companies the page lists (the report keeps up to 30 so the market-cap range has some to pick
 * from). */
const SHOWN_NAMES = 12;

function Detail({ t, r, ranges }: { t: LibraryTheme; r: ThemesReport; ranges: Record<"us" | "in", CapRange> }) {
  const markets = (["us", "in"] as const).filter((m) => t.names.some((n) => n.market === m));
  const names = t.names.filter((n) => inCapRange(n.cap, CAP_STEPS[n.market], ranges[n.market])).slice(0, SHOWN_NAMES);
  const capped = t.names.some((n) => n.cap !== undefined);
  const from = t.driver === "filings" ? "Company filings" : (r.drivers[t.driver] ?? t.driver);
  const big = t.chart.some(([, v]) => Math.abs(v) >= 10000);
  const history = historyLine(t.history);
  return (
    <>
      <Link href="/themes" className="inline-flex min-h-11 items-center gap-1.5 self-start text-[14px] font-medium no-underline md:min-h-0">
        <Icon name="chevron-left" />
        All themes
      </Link>
      <section aria-labelledby="theme-title" className="sheet rise flex flex-col gap-5 p-5 md:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <span className="eyebrow">{t.category}</span>
          <StatusChip s={t.status} full />
          {t.origin === "ai" && t.born ? <span className="text-[12px] text-subtle">added by the AI {shortDate(t.born, true)}</span> : null}
        </div>
        <h2 id="theme-title" className="text-[26px] leading-tight font-bold tracking-[-0.02em] text-fg md:text-[32px]">
          {t.title}
        </h2>
        <p className="max-w-3xl text-[16px] leading-relaxed text-fg">{t.why}</p>
        <ol aria-label="The chain" className="flex flex-col gap-2 md:flex-row md:items-stretch">
          <Step tone="bg-tint-sky" head="The trigger" body={from} sub={readingWords(t)} />
          <Arrow text={lagWords(t)} />
          <Step tone="bg-tint-sage" head="Who it lifts" body={t.keywords.join(", ")} sub={`${t.companies} companies${t.markets.length ? ` · ${t.markets.map(marketName).join(" and ")}` : ""}`} />
        </ol>
        {basisLines(t, r).length > 0 ? (
          <Disclosure summary={<><Icon name="info" /> The data behind it</>} className="rounded-tile bg-raised px-4 py-2">
            <div className="flex flex-col gap-1.5 pb-1 text-[14px] text-fg">
              {basisLines(t, r).map((l) => (
                <p key={l}>{l}</p>
              ))}
            </div>
          </Disclosure>
        ) : null}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="The trigger now" value={t.signal} sub={zWords(t.z)} />
          <Stat label="Demand evidence" value={`${t.with_demand} of ${t.companies}`} sub="companies report it" />
          <Stat label="Price, 12 months" value={pct(t.move)} sub={t.market_move === null ? "" : `market ${pct(t.market_move)}`} />
          <Stat label="Undervalued" value={String(t.undervalued)} sub="on the board or Watch" />
        </div>
        {history ? <p className="rounded-tile bg-raised px-4 py-3 text-[14px] text-muted">{history} Today&apos;s companies only, so it flatters.</p> : null}
        <p className="flex items-start gap-2 text-[14px] text-muted">
          <Icon name="alert" className="mt-0.5 text-warn" />
          <span>
            <span className="font-semibold text-fg">Wrong if: </span>
            {t.wrong_if}
          </span>
        </p>
      </section>
      <div className="grid items-start gap-6 lg:grid-cols-[3fr_2fr]">
        <Section id="names" title="The companies" description="Undervalued names first, then by Evidence.">
          {capped && markets.length > 0 ? (
            <div className="mb-3 flex flex-wrap gap-x-8 gap-y-4">
              {markets.map((m) => (
                <CapRangeLink
                  key={m}
                  market={m}
                  steps={CAP_STEPS[m]}
                  value={ranges[m]}
                  param={`cap_${m}`}
                  note={markets.length > 1 ? `${marketName(m)}: market cap as of the latest scored week.` : "Market cap as of the latest scored week."}
                />
              ))}
            </div>
          ) : null}
          {t.names.length === 0 ? (
            <Empty>No company in the universe matches this theme yet.</Empty>
          ) : names.length === 0 ? (
            <Empty>None of this theme&apos;s companies is in that market-cap range.</Empty>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {names.map((n) => (
                <li key={n.company_id}>
                  <Link
                    href={`/company/${n.company_id}`}
                    className="press tile flex items-center gap-3 px-3 py-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[14px] font-bold">
                        {n.code ?? ""} <span className="font-medium text-muted">{n.name}</span>
                      </span>
                      <span className="truncate text-[12px] text-subtle">
                        {marketName(n.market)} · {n.industry}
                        {n.cap ? ` · ${capText(n.market, n.cap)}` : ""}
                        {n.demand ? " · reports demand" : ""}
                      </span>
                    </span>
                    {n.bucket === "candidate" || n.bucket === "watch" ? (
                      <span className="rounded-full bg-tint-sage px-2 py-0.5 text-[11px] font-semibold text-up">{n.bucket === "candidate" ? "On the board" : "Watch"}</span>
                    ) : null}
                    <span className={cn("num w-12 shrink-0 text-right text-[13px] font-semibold", (n.move ?? 0) >= 0 ? "text-up" : "text-down")}>{pct(n.move)}</span>
                    <LinkPending />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <div className="flex min-w-0 flex-col gap-6">
          {t.chart.length > 0 ? (
            <LineChartCard
              title={from}
              data={t.chart.map(([m, v]) => ({ period: `${m}-01`, value: v }))}
              series={[{ key: "value", label: from }]}
              format={big ? "big" : "num"}
              surface="sheet"
              note="Monthly, the last ten years (FRED)."
            />
          ) : null}
          <Section id="notes" title="How it evolved" description="The AI's notes at each rethink, newest first.">
            {t.notes.length === 0 ? (
              <p className="text-[14px] text-muted">A starter theme: the first rethink will say whether it stays.</p>
            ) : (
              <Notes notes={t.notes} />
            )}
          </Section>
        </div>
      </div>
    </>
  );
}

function Step({ tone, head, body, sub }: { tone: string; head: string; body: string; sub: string }) {
  return (
    <li className={cn("flex min-w-0 flex-1 flex-col gap-1 rounded-tile p-4", tone)}>
      <span className="text-[12px] font-semibold tracking-[0.06em] text-muted uppercase">{head}</span>
      <span className="text-[16px] font-bold text-fg">{body}</span>
      <span className="text-[13px] text-muted">{sub}</span>
    </li>
  );
}

function Arrow({ text }: { text: string }) {
  return (
    <li aria-label={text} className="flex shrink-0 items-center justify-center gap-1.5 px-2 text-[13px] font-semibold text-muted md:flex-col">
      <Icon name="chevron-right" className="rotate-90 md:rotate-0" strokeWidth={2.4} />
      <span>{text}</span>
    </li>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-tile bg-raised p-3.5">
      <span className="text-[12px] font-medium text-muted">{label}</span>
      <span className="num text-[18px] leading-tight font-bold text-fg">{value}</span>
      {sub ? <span className="text-[12px] text-subtle">{sub}</span> : null}
    </div>
  );
}

const DECISION: Record<string, string> = { keep: "Kept", edit: "Edited", retire: "Retired", new: "Added" };

function Notes({ notes }: { notes: LibraryTheme["notes"] }) {
  return (
    <ol className="flex flex-col">
      {[...notes].reverse().map((n, i) => (
        <li key={`${n.week}-${i}`} className="flex flex-col gap-0.5 border-t border-line py-3 first:border-t-0 first:pt-0">
          <span className="text-[12px] text-subtle">
            {shortDate(n.week, true)} · <span className="font-semibold text-fg">{DECISION[n.decision] ?? n.decision}</span>
          </span>
          <span className="text-[14px] text-fg">{n.text}</span>
        </li>
      ))}
    </ol>
  );
}

function Retired({ t }: { t: RetiredTheme }) {
  return (
    <>
      <Link href="/themes" className="inline-flex min-h-11 items-center gap-1.5 self-start text-[14px] font-medium no-underline md:min-h-0">
        <Icon name="chevron-left" />
        All themes
      </Link>
      <Section id="retired" eyebrow={`${t.category} · retired ${shortDate(t.week, true)}`} title={t.title} description={t.note}>
        <Notes notes={t.notes} />
      </Section>
    </>
  );
}
