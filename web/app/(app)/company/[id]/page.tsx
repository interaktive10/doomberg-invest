import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { ChartGrid, LineChartCard, type Format, type Row, type Series } from "@/components/charts";
import { Chip } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { FactItem } from "@/components/fact";
import { Icon } from "@/components/icons";
import { KillList } from "@/components/kill-list";
import { Meter } from "@/components/meter";
import { OpenTarget } from "@/components/open-target";
import { Empty, Flash, FRAME, Section } from "@/components/page";
import { WhyThisScore } from "@/components/score";
import { ScoreRing, type ScoreKind } from "@/components/score-ring";
import { SubmitButton } from "@/components/submit-button";
import { TickerTile } from "@/components/ticker-tile";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import {
  company as getCompany,
  companySeries,
  events,
  facts,
  fundamentals,
  insiders,
  killCriteria,
  latestScore,
  thesesOf,
  thesis as getThesis,
  whyScore,
  type Bucket,
} from "@/lib/data";
import { shortDate } from "@/lib/dates";
import {
  BOARD_LABEL,
  bucketLine,
  caseLine,
  INSIDER_ROWS,
  insidersCapped,
  insiderSummary,
  insiderTotal,
  money,
  trendNote,
  whenLine,
  type InsiderEvent,
  type InsiderGroup,
} from "@/lib/explain";
import { big, code } from "@/lib/format";
import { one, UUID, type Query } from "@/lib/forms";
import { detailText, humanize } from "@/lib/labels";
import { chartRows } from "@/lib/metrics";
import type { ChartTone, Tone } from "@/lib/palette";
import { killCheckLine, LIVE_STATES, STATE_LABEL } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { research } from "../../candidates/actions";

// BRIEF §6 Company, redrawn (overhaul PR 6, the Company mock): a header sheet with the ticker, the name, the case in one
// line (the live card's summary, else what its bucket means), the Evidence and Gap rings, the bucket (no family dots
// beside it: Why this score names the kinds; PR 6 final review EYE-19) and the next step (open the card, or Research);
// then Why this score (components/score.tsx) beside What would kill it (the live thesis's kill criteria), the
// insiders' buying as bars and the corporate events; the business quarter by quarter as sparkline cards (the weekly
// run's company_series, §4.6 definitions); the verified facts as quotes, folded.

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function score100(v: number | string | null | undefined): number | null {
  const x = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : Number.NaN;
  return Number.isFinite(x) ? x : null;
}

const BUCKET_BADGE: Record<Bucket, "default" | "secondary" | "destructive" | "outline"> = {
  candidate: "default",
  early: "secondary",
  watch: "secondary",
  priced_in: "secondary",
  excluded: "destructive",
  none: "outline",
};

/** The quarterly charts, in the order a reader asks: is it growing, is it profitable, is the cash real, is it diluting,
 * is it levered, is there an order book. One shows only when its series has a value. Each has its own colour, as the
 * Company mock: sales in the accent, profitability in the business green, cash in the insiders blue. */
const CHARTS: { title: string; format: Format; tone: ChartTone; series: Series[] }[] = [
  { title: "Revenue (TTM)", format: "money", tone: "accent", series: [{ key: "revenue", label: "Revenue" }] },
  { title: "Operating margin (TTM)", format: "pct", tone: "business", series: [{ key: "opm", label: "Operating margin" }] },
  {
    title: "Return on capital",
    format: "pct",
    tone: "business",
    series: [
      { key: "roic", label: "ROIC" },
      { key: "incremental_roic", label: "On new capital" },
    ],
  },
  { title: "Cash conversion", format: "x", tone: "insiders", series: [{ key: "ccr", label: "Cash from operations / net income" }] },
  { title: "Diluted shares", format: "big", tone: "ownership", series: [{ key: "shares", label: "Shares" }] },
  { title: "Net debt / EBITDA", format: "x", tone: "text", series: [{ key: "nd_ebitda", label: "Net debt / EBITDA" }] },
  { title: "Order book", format: "money", tone: "accent", series: [{ key: "order_book", label: "Order book" }] },
];

/** A link that stands alone in small text: 44 px tall on a phone (a thumb's target), its own height from md up. */
const SMALL_LINK = "inline-flex min-h-11 items-center md:min-h-0";

const KIND_WORD: Record<string, string> = {
  open_market_buy: "bought",
  open_market_sell: "sold",
  promoter_buy: "promoter bought",
  promoter_sell: "promoter sold",
  pledge_created: "pledge created",
  pledge_released: "pledge released",
};

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const c = UUID.test(id) ? await getCompany(id) : null;
  return { title: c ? `${c.name} (${code(c)})` : "Company" };
}

function Ring({ kind, value }: { kind: ScoreKind; value: number | null }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <ScoreRing value={value} kind={kind} size={76} />
      <span aria-hidden="true" className="text-[13px] font-semibold text-fg">
        {kind === "evidence" ? "Evidence" : "Gap"}
      </span>
    </div>
  );
}

/** One side's trades as a bar per person (most money first, five at most), then when and how; `capped` when the read
 * stopped at its latest filings, so older trades of the year may be missing. */
function InsiderBars({ g, tone, how, capped }: { g: InsiderGroup; tone: Tone; how: string; capped: boolean }) {
  const max = Math.max(...g.people.map((p) => p.value), 1);
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {g.people.slice(0, 5).map((p) => (
          <li key={p.who} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3 text-[14px]">
              <span className="min-w-0">
                <span className="font-semibold text-fg">{p.who}</span>
                {p.role ? <span className="text-subtle"> {p.role}</span> : null}
              </span>
              <span className="num shrink-0 font-semibold text-fg">{money(p.value, g.currency)}</span>
            </div>
            <Meter value={p.value} max={max} tone={tone} />
          </li>
        ))}
      </ul>
      {g.people.length > 5 ? <p className="text-[13px] text-subtle">and {g.people.length - 5} more</p> : null}
      <p className="text-[13px] text-subtle">
        {whenLine(g)}, {how}
        {g.planned > 0 ? `; ${g.planned} planned in advance` : ""}
        {capped ? `; from the latest ${INSIDER_ROWS} filings only` : ""}
      </p>
    </div>
  );
}

/** A corporate event in one row: what, when, the detail and its source. */
function EventRow({ e }: { e: Record<string, unknown> }) {
  return (
    <li className="flex flex-col gap-0.5 border-t border-line py-2.5 first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-3 text-[14px]">
        <span className="font-semibold text-fg">{humanize(str(e.kind))}</span>
        <span className="num shrink-0 text-[13px] text-subtle">{shortDate(str(e.event_date), true)}</span>
      </div>
      {detailText(e.detail) ? <p className="text-[13px] break-words text-muted">{detailText(e.detail)}</p> : null}
      {e.source_url ? (
        <a href={str(e.source_url)} rel="noreferrer" target="_blank" className={cn(SMALL_LINK, "self-start text-[13px]")}>
          source<span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
    </li>
  );
}

export default async function CompanyPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const { id } = await params;
  const q = await searchParams;
  if (!UUID.test(id)) notFound();
  const c = await getCompany(id);
  if (c === null) notFound();
  const [rows, ins, evs, fs, ths, ser, score] = await Promise.all([
    fundamentals(id),
    insiders(id),
    events(id),
    facts([id], 30),
    thesesOf(id),
    companySeries(id),
    latestScore(id),
  ]);
  const live = ths.find((t) => (LIVE_STATES as readonly string[]).includes(t.state));
  // The live thesis's card (its one-line case) and kill criteria: the Thesis page's own reads, unchanged.
  const [why, card, kills] = await Promise.all([
    score ? whyScore(id, score) : null,
    live ? getThesis(live.id) : null,
    live ? killCriteria(live.id) : [],
  ]);
  const data: Row[] = chartRows(ser?.points ?? []).map((p) => ({ ...p }));
  const currency = rows.find((r) => r.currency)?.currency ?? (c.market === "us" ? "USD" : "INR");
  const ticker = code(c);
  const line = caseLine(card?.card_json, card?.card_md) ?? bucketLine(score?.bucket);
  const past = ths.filter((t) => t.id !== live?.id);
  const charts = CHARTS.filter((ch) => data.some((r) => ch.series.some((s) => typeof r[s.key] === "number")));
  const trades: InsiderEvent[] = ins.map((e) => ({
    event_date: str(e.event_date),
    filed_at: e.filed_at ? str(e.filed_at) : null,
    person: str(e.person),
    role: e.role ? str(e.role) : null,
    kind: str(e.kind),
    value: typeof e.value === "number" || typeof e.value === "string" ? e.value : null,
    currency: e.currency ? str(e.currency) : null,
    planned: e.planned === true,
    source_url: e.source_url ? str(e.source_url) : null,
    amends: e.amends ? str(e.amends) : null,
  }));
  const { bought, sold } = insiderSummary(trades, currency);
  const capped = insidersCapped(ins.length);
  const noteHref = live ? `/theses/${live.id}#journal` : "/journal#add-note";

  const side: ReactNode[] = [];
  if (kills.length > 0) {
    side.push(
      <Section
        key="kill"
        title="What would kill it"
        id="kill"
        description={killCheckLine(kills)}
      >
        <KillList kills={kills} />
      </Section>,
    );
  }
  if (ins.length > 0) {
    side.push(
      <Section
        key="insiders"
        title={bought ? "Insiders bought" : sold ? "Insiders sold" : "Insiders"}
        id="insiders"
        actions={
          bought || sold ? <span className="num text-[15px] font-bold text-fg">{insiderTotal((bought ?? sold)!, capped)}</span> : undefined
        }
      >
        <div className="flex flex-col gap-4">
          {bought ? <InsiderBars g={bought} tone="insiders" how="on the open market" capped={capped} /> : null}
          {bought && sold ? (
            <h3 className="eyebrow">
              Sold <span className="num">{insiderTotal(sold, capped)}</span>
            </h3>
          ) : null}
          {sold ? <InsiderBars g={sold} tone="down" how="on the open market" capped={capped} /> : null}
          {!bought && !sold ? <p className="text-[14px] text-muted">No open-market trades; the filings are below.</p> : null}
          <Disclosure summary="The filings">
            <ul className="flex flex-col">
              {ins.map((e) => (
                <li key={str(e.id)} className="flex flex-col gap-0.5 border-t border-line py-2.5 text-[13px] first:border-t-0 first:pt-0">
                  <span className="text-fg">
                    <span className="font-semibold">{str(e.person)}</span> {KIND_WORD[str(e.kind)] ?? humanize(str(e.kind)).toLowerCase()}
                    {e.planned ? " (planned)" : ""}
                  </span>
                  <span className="num">
                    {shortDate(str(e.event_date), true)}
                    {e.shares === null || e.shares === undefined ? "" : ` · ${big(e.shares as number)} shares`}
                    {e.value === null || e.value === undefined ? "" : ` · ${money(Number(e.value), str(e.currency) || currency)}`}
                    {e.source_url ? (
                      <>
                        {" · "}
                        <a href={str(e.source_url)} rel="noreferrer" target="_blank" className={SMALL_LINK}>
                          filing<span className="sr-only"> (opens in a new tab)</span>
                        </a>
                      </>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </Disclosure>
        </div>
      </Section>,
    );
  }
  if (evs.length > 0) {
    side.push(
      <Section key="events" title="Events" id="events" count={evs.length}>
        <ul className="flex flex-col">
          {evs.slice(0, 3).map((e) => (
            <EventRow key={str(e.id)} e={e} />
          ))}
        </ul>
        {evs.length > 3 ? (
          <Disclosure summary={`${evs.length - 3} more`}>
            <ul className="flex flex-col">
              {evs.slice(3).map((e) => (
                <EventRow key={str(e.id)} e={e} />
              ))}
            </ul>
          </Disclosure>
        ) : null}
      </Section>,
    );
  }
  if (past.length > 0) {
    side.push(
      <Section key="theses" title="Earlier theses" id="theses" quiet>
        <ul className="flex flex-col">
          {past.map((t) => (
            <li key={t.id} className="border-t border-line first:border-t-0">
              <Link href={`/theses/${t.id}`} className="link-quiet flex min-h-11 items-center justify-between gap-3 text-[14px]">
                <span>
                  {STATE_LABEL[t.state]} · card of {shortDate(t.created_week, true)}
                </span>
                <Icon name="chevron-right" className="text-subtle" />
              </Link>
            </li>
          ))}
        </ul>
      </Section>,
    );
  }

  return (
    <main id="main" className={cn(FRAME, "flex flex-col gap-6 pt-3 pb-8 md:pt-4")}>
      <Link href="/candidates" className="inline-flex min-h-11 items-center gap-1.5 self-start text-[14px] font-medium no-underline md:min-h-0">
        <Icon name="chevron-left" />
        Candidates
      </Link>

      <header className="sheet rise flex flex-wrap items-center gap-5 p-5 md:gap-6 md:p-7">
        <TickerTile ticker={ticker} size="lg" />
        <div className="flex min-w-[min(100%,16rem)] flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[28px] leading-[1.1] font-bold tracking-[-0.03em] text-fg md:text-[34px]">
              {c.name}
              <span className="sr-only"> ({ticker})</span>
            </h1>
            {score ? <Badge variant={BUCKET_BADGE[score.bucket] ?? "outline"}>{BOARD_LABEL[score.bucket] ?? humanize(score.bucket)}</Badge> : null}
          </div>
          <p className="text-[14px] text-subtle">
            {[ticker, c.sector, c.industry].filter(Boolean).join(" · ")} · {c.market === "us" ? "US" : "India"}
          </p>
          <p className="mt-1 max-w-[620px] text-[16px] leading-normal text-fg">{line}</p>
          {c.in_universe ? null : (
            <Chip variant="warn" className="mt-1 self-start">
              Outside the universe{c.excluded_reason ? `: ${c.excluded_reason}` : ""}
            </Chip>
          )}
        </div>
        <div className="flex items-center gap-4">
          <Ring kind="evidence" value={score100(score?.evidence)} />
          <Ring kind="gap" value={score100(score?.gap)} />
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto">
          {live ? (
            <Link href={`/theses/${live.id}`} className={cn(buttonVariants(), "w-full")}>
              {live.state === "research" ? "Open research card" : "Open thesis"}
            </Link>
          ) : (
            <form action={research} className="w-full">
              <input type="hidden" name="company_id" value={c.id} />
              <input type="hidden" name="back" value={`/company/${c.id}`} />
              <SubmitButton className="w-full">Research</SubmitButton>
            </form>
          )}
          <Link href={noteHref} className={cn(buttonVariants({ variant: "secondary" }), "w-full")}>
            Add journal note
          </Link>
        </div>
      </header>

      <Flash error={one(q, "error")} ok={one(q, "ok")} />

      <div className="flex flex-wrap items-start gap-6">
        <WhyThisScore score={score} why={why} className="flex-[999_1_560px]" />
        {side.length > 0 ? <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">{side}</div> : null}
      </div>

      <Section
        plain
        title="The business, quarter by quarter"
        id="fundamentals"
        description={charts.length > 0 && ser ? `Money in ${currency}, as of the week scored ${shortDate(ser.week_end, true)}.` : undefined}
      >
        {charts.length === 0 ? (
          <Empty>No quarterly series yet: the weekly scoring run computes them.</Empty>
        ) : (
          <ChartGrid className="gap-5">
            {charts.map((ch) => (
              <LineChartCard
                key={ch.title}
                title={ch.title}
                data={data}
                series={ch.series}
                format={ch.format}
                currency={currency}
                tone={ch.tone}
                surface="sheet"
                note={trendNote(
                  data.map((r) => {
                    const v = r[ch.series[0]!.key];
                    return typeof v === "number" ? v : null;
                  }),
                  ch.format,
                )}
              />
            ))}
          </ChartGrid>
        )}
      </Section>

      {fs.length > 0 ? (
        <Section title="Verified facts" id="facts" count={fs.length} description="Each one matched word for word in its filing.">
          <OpenTarget />
          <Disclosure summary="Show the quotes">
            <ul className="flex flex-col gap-2">
              {fs.map((f) => (
                <FactItem key={f.id} f={f} />
              ))}
            </ul>
          </Disclosure>
        </Section>
      ) : null}
    </main>
  );
}
