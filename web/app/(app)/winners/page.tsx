import Link from "next/link";
import { LinkPending } from "@/components/link-pending";
import { Empty, Page } from "@/components/page";
import { requireUser } from "@/lib/auth";
import { latestReport } from "@/lib/data";
import { dayDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import {
  barScale,
  capFloor,
  grewTo,
  marketName,
  signedPct,
  verdict,
  type BacktestRow,
  type MarketWinners,
  type WinnerPick,
  type WinnersReport,
} from "@/lib/winners";

export const metadata = { title: "Winners" };

// Last year's winners (docs/SPEC_ISSUES.md 64): the claim first (does buying last year's five pay?), tested on our own
// prices, then each market's five with how they are doing this year. One report row, computed every Saturday.
export default async function Winners() {
  await requireUser();
  const report = await latestReport<WinnersReport>("winners");
  const markets = report?.body.markets ?? [];
  const tested = markets.find((m) => m.backtest?.summary);
  const through = markets.map((m) => m.this_year.through).find(Boolean);
  const year = markets[0] ? markets[0].year + 1 : null;
  return (
    <Page title="Winners" description="This year's biggest gainers to watch for next January, and how last year's are doing.">
      {markets.length === 0 ? (
        <Empty>The first winners report is computed on Saturday.</Empty>
      ) : (
        <>
          <section aria-labelledby="leaders" className="flex flex-col gap-3">
            <div className="flex flex-col gap-0.5">
              <h2 id="leaders" className="text-[22px] font-bold tracking-[-0.02em] text-fg">
                {year} so far
              </h2>
              <p className="text-[14px] text-muted">
                The biggest gainers this year{through ? ` (to ${dayDate(through)})` : ""}. If the pattern holds, these are next January&apos;s buys.
              </p>
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              {markets.map((m) => (
                <LeadersCard key={m.market} m={m} />
              ))}
            </div>
          </section>
          <section aria-labelledby="last-year" className="flex flex-col gap-3">
            <div className="flex flex-col gap-0.5">
              <h2 id="last-year" className="text-[22px] font-bold tracking-[-0.02em] text-fg">
                {markets[0]!.year}&apos;s top 5, this year
              </h2>
              <p className="text-[14px] text-muted">Last year&apos;s biggest gainers and how they are doing since January: the strategy, live.</p>
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              {markets.map((m) => (
                <MarketCard key={m.market} m={m} />
              ))}
            </div>
          </section>
          {tested ? <StrategyTest m={tested} /> : null}
          <p className="text-[13px] text-subtle">
            Price change only (no dividends). A name counts only if it was investable: at least $5 / Rs 20 when the year began
            and a market value above the size floor at the end. Today&apos;s companies only: a past winner that later collapsed and
            delisted is missing, which flatters the test{report ? ` · computed ${dayDate(report.week_end)}` : ""}.
          </p>
        </>
      )}
    </Page>
  );
}

/** A market's ten biggest gainers this year so far: the list to watch. */
function LeadersCard({ m }: { m: MarketWinners }) {
  const list = m.leaders ?? [];
  return (
    <section aria-labelledby={`leaders-${m.market}`} className="sheet flex min-w-0 flex-col gap-4 p-5 md:p-6">
      <div className="flex items-baseline justify-between gap-2">
        <h3 id={`leaders-${m.market}`} className="text-[18px] font-bold text-fg">
          {marketName(m.market)}
        </h3>
        <span className="text-[13px] text-subtle">above {capFloor(m)}</span>
      </div>
      {list.length === 0 ? (
        <Empty>No price for this year yet.</Empty>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {list.map((p, i) => (
            <li key={p.company_id}>
              <Link
                href={`/company/${p.company_id}`}
                className="press tile flex items-center gap-3 px-3 py-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
              >
                <span aria-hidden="true" className="num w-6 shrink-0 text-center text-[14px] font-bold text-subtle">
                  {i + 1}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[15px] font-bold">
                    {p.code ?? ""} <span className="font-medium text-muted">{p.name}</span>
                  </span>
                  <span className="truncate text-[12px] text-subtle">{p.sector ?? "No sector"}</span>
                </span>
                <span className={cn("num shrink-0 text-[20px] font-bold tracking-[-0.02em]", gainTone(p.ytd))}>{signedPct(p.ytd)}</span>
                <LinkPending />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Gains green, losses red: the one meaning colour carries on this screen. */
function gainTone(v: number | null | undefined): string {
  return v === null || v === undefined ? "text-subtle" : v >= 0 ? "text-up" : "text-down";
}

const NUMBER: Record<number, string> = { 2: "two", 3: "three", 4: "four", 5: "five" };

const VERDICT_TONE = { up: "text-up", down: "text-down", flat: "text-warn" } as const;

/** The claim, tested: a verdict in two words, what $100 became each way, and one bar pair a year. */
function StrategyTest({ m }: { m: MarketWinners }) {
  const s = m.backtest!.summary!;
  const v = verdict(s);
  const rows = m.backtest!.rows;
  const scale = barScale(rows);
  return (
    <section aria-labelledby="test" className="sheet rise flex flex-col gap-5 overflow-hidden p-5 md:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="eyebrow">The test · {marketName(m.market)} · {s.first}–{s.last}</p>
          <h2 id="test" className="text-[22px] font-bold tracking-[-0.02em] text-fg md:text-[26px]">
            Buy last year&apos;s top 5 every January: <span className={VERDICT_TONE[v.tone]}>{v.title.toLowerCase()}</span>
          </h2>
          <p className="text-[15px] text-muted">{v.line}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Grew label="Last year's top 5" value={grewTo(s.growth)} rate={signedPct(s.cagr)} strong />
        <Grew label="The average stock" value={grewTo(s.average_growth)} rate={signedPct(s.average_cagr)} />
        <div className="col-span-2 flex flex-col gap-1 rounded-tile bg-raised p-4 md:col-span-1">
          <span className="text-[13px] font-medium text-muted">Years ahead</span>
          <span className="num text-[30px] leading-none font-bold tracking-[-0.03em] text-fg md:text-[36px]">
            {s.beat}
            <span className="text-[18px] font-semibold text-subtle"> of {s.years}</span>
          </span>
          <span className="text-[13px] text-muted">
            best {s.best} · worst {s.worst}
          </span>
        </div>
      </div>
      <YearBars rows={rows} scale={scale} />
    </section>
  );
}

function Grew({ label, value, rate, strong = false }: { label: string; value: string; rate: string; strong?: boolean }) {
  return (
    <div className={cn("flex flex-col gap-1 rounded-tile p-4", strong ? "bg-tint-sky" : "bg-raised")}>
      <span className="text-[13px] font-medium text-muted">{label}</span>
      <span className="num text-[30px] leading-none font-bold tracking-[-0.03em] text-fg md:text-[36px]">{value}</span>
      <span className="text-[13px] text-muted">
        from $100 · <span className="num font-semibold text-fg">{rate}</span> a year
      </span>
    </div>
  );
}

/** One row a year: the picks' return (indigo) over the average's (grey), from a centre line, so a losing year points
 * left. */
function YearBars({ rows, scale }: { rows: BacktestRow[]; scale: number }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-4 text-[12px] text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 rounded-full bg-accent" /> Top 5
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 rounded-full bg-edge" /> Average stock
        </span>
      </div>
      <ul className="flex flex-col gap-1.5" aria-label="Each year">
        {rows.map((r, i) => (
          <li key={r.year} className="grid grid-cols-[2.75rem_1fr_6.5rem] items-center gap-3 text-[13px]">
            <span className="num font-semibold text-muted">{r.year}</span>
            <span className="flex flex-col gap-[3px]" aria-hidden="true">
              <Bar v={r.ret} scale={scale} tone="bg-accent" i={i} />
              <Bar v={r.average} scale={scale} tone="bg-edge/70" i={i} />
            </span>
            <span className="num text-right whitespace-nowrap">
              <span className={cn("font-semibold", gainTone(r.ret))}>{signedPct(r.ret)}</span>
              <span className="text-subtle"> vs {signedPct(r.average)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Bar({ v, scale, tone, i }: { v: number; scale: number; tone: string; i: number }) {
  const w = Math.min(50, (Math.abs(v) / scale) * 50);
  return (
    <span className="relative block h-2 rounded-full bg-track/60">
      <span aria-hidden="true" className="absolute top-0 left-1/2 h-full w-px bg-line-strong" />
      <span
        className={cn("grow-x absolute top-0 h-full rounded-full", tone)}
        style={{ width: `${w}%`, left: v >= 0 ? "50%" : `${50 - w}%`, animationDelay: `${i * 30}ms` }}
      />
    </span>
  );
}

/** A market's five: rank, name, last year's gain big, and this year so far. */
function MarketCard({ m }: { m: MarketWinners }) {
  const ty = m.this_year;
  return (
    <section aria-labelledby={`top-${m.market}`} className="sheet flex min-w-0 flex-col gap-4 p-5 md:p-6">
      <div className="flex items-baseline justify-between gap-2">
        <h3 id={`top-${m.market}`} className="text-[18px] font-bold text-fg">
          {marketName(m.market)}
        </h3>
        <span className="text-[13px] text-subtle">above {capFloor(m)}</span>
      </div>
      {ty.picks !== null && ty.average !== null && ty.through ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1 rounded-tile bg-raised p-3.5">
            <span className="text-[12px] font-medium text-muted">
              {m.top.length === 1 ? "This one" : `These ${NUMBER[m.top.length] ?? m.top.length}`}, this year
            </span>
            <span className={cn("num text-[28px] leading-none font-bold tracking-[-0.03em]", gainTone(ty.picks))}>{signedPct(ty.picks)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-tile bg-raised p-3.5">
            <span className="text-[12px] font-medium text-muted">The average stock</span>
            <span className={cn("num text-[28px] leading-none font-bold tracking-[-0.03em]", gainTone(ty.average))}>{signedPct(ty.average)}</span>
          </div>
        </div>
      ) : null}
      {m.top.length === 0 ? (
        <Empty>No company cleared the bar for {m.year}.</Empty>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div aria-hidden="true" className="flex items-center gap-3 px-3 text-[11px] font-semibold tracking-[0.06em] text-subtle uppercase">
            <span className="flex-1">Company</span>
            <span className="w-16 text-right">{m.year}</span>
            <span className="w-20 text-right">This year</span>
          </div>
          <ol className="flex flex-col gap-1.5">
            {m.top.map((p) => (
              <PickRow key={p.company_id} p={p} year={m.year} />
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

/** Last year's gain, then this year's (the one to watch, bigger), each green or red by sign. */
function PickRow({ p, year }: { p: WinnerPick; year: number }) {
  return (
    <li>
      <Link
        href={`/company/${p.company_id}`}
        className="press tile flex items-center gap-3 px-3 py-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
      >
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[15px] font-bold">
            {p.code ?? ""} <span className="font-medium text-muted">{p.name}</span>
          </span>
          <span className="truncate text-[12px] text-subtle">{p.sector ?? "No sector"}</span>
        </span>
        <span className={cn("num w-16 shrink-0 text-right text-[14px] font-semibold", gainTone(p.ret))}>
          <span className="sr-only">{year}: </span>
          {signedPct(p.ret)}
        </span>
        <span className={cn("num w-20 shrink-0 text-right text-[20px] font-bold tracking-[-0.02em]", gainTone(p.ytd))}>
          <span className="sr-only">this year: </span>
          {signedPct(p.ytd)}
        </span>
        <LinkPending />
      </Link>
    </li>
  );
}
