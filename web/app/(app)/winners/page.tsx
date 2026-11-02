import { Empty, Freshness, Page } from "@/components/page";
import { WinnersMarket } from "@/components/winners-market";
import { requireUser } from "@/lib/auth";
import { latestReport } from "@/lib/data";
import { dayDate } from "@/lib/dates";
import { nextRunDate } from "@/lib/schedule";
import { cn } from "@/lib/utils";
import {
  barScale,
  gainTone,
  grewTo,
  marketName,
  signedPct,
  verdict,
  type BacktestRow,
  type MarketWinners,
  type WinnersReport,
} from "@/lib/winners";

export const metadata = { title: "Winners" };

// Winners (docs/SPEC_ISSUES.md 64): per market, a market-cap slider over this year's ten biggest gainers (next January's
// list) and last year's five with how they are doing this year; then the test of the strategy. One report row, computed
// every weekday evening on the latest closes (docs/SPEC_ISSUES.md 75).
export default async function Winners() {
  await requireUser();
  const report = await latestReport<WinnersReport>("winners");
  const markets = report?.body.markets ?? [];
  const tested = markets.find((m) => m.backtest?.summary);
  const at = (m: "us" | "in") => markets.find((x) => x.market === m)?.this_year.through ?? null;
  return (
    <Page
      title="Winners"
      description="This year's biggest gainers to watch for next January, and how last year's are doing."
      freshness={
        markets.length > 0 ? (
          <Freshness
            items={[
              { label: "US prices to", date: at("us") },
              { label: "India prices to", date: at("in") },
            ]}
            next={nextRunDate("closes", new Date())}
          />
        ) : null
      }
    >
      {markets.length === 0 ? (
        <Empty>The first winners report is computed on Saturday.</Empty>
      ) : (
        <>
          {markets.map((m) => (
            <WinnersMarket key={m.market} m={m} />
          ))}
          {tested ? <StrategyTest m={tested} /> : null}
          <p className="text-[13px] text-subtle">
            Price change only (no dividends). A name counts only if it was investable: at least $5 / Rs 20 when the year began
            and a market value above the size floor at the end. Today&apos;s companies only: a past winner that later collapsed and
            delisted is missing, which flatters the test{report ? ` · computed ${dayDate(report.body.as_of)}` : ""}.
          </p>
        </>
      )}
    </Page>
  );
}

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
