import Link from "next/link";
import { LinkPending } from "@/components/link-pending";
import { Icon } from "@/components/icons";
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
  return (
    <Page
      title="Winners"
      description="Last year's biggest gainers, and whether buying them pays."
    >
      {markets.length === 0 ? (
        <Empty>The first winners report is computed on Saturday.</Empty>
      ) : (
        <>
          {tested ? <StrategyTest m={tested} /> : null}
          <div className="grid gap-6 lg:grid-cols-2">
            {markets.map((m) => (
              <MarketCard key={m.market} m={m} />
            ))}
          </div>
          <p className="text-[13px] text-subtle">
            Price change only (no dividends), January to December. A winner had to be investable: at least $5 / Rs 20 when the
            year began and a market value above the size floor when it ended. Today&apos;s companies only: a past winner that
            later collapsed and delisted is missing, which flatters the test{report ? ` · computed ${dayDate(report.week_end)}` : ""}.
          </p>
        </>
      )}
    </Page>
  );
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
    <div className={cn("flex flex-col gap-1 rounded-tile p-4", strong ? "bg-tint-rose" : "bg-raised")}>
      <span className="text-[13px] font-medium text-muted">{label}</span>
      <span className="num text-[30px] leading-none font-bold tracking-[-0.03em] text-fg md:text-[36px]">{value}</span>
      <span className="text-[13px] text-muted">
        from $100 · <span className="num font-semibold text-fg">{rate}</span> a year
      </span>
    </div>
  );
}

/** One row a year: the picks' return (pink) over the average's (grey), from a centre line, so a losing year points
 * left. */
function YearBars({ rows, scale }: { rows: BacktestRow[]; scale: number }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-4 text-[12px] text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 rounded-full bg-pink" /> Top 5
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
              <Bar v={r.ret} scale={scale} tone="bg-pink" i={i} />
              <Bar v={r.average} scale={scale} tone="bg-edge/70" i={i} />
            </span>
            <span className="num text-right whitespace-nowrap">
              <span className="font-semibold text-fg">{signedPct(r.ret)}</span>
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
      <div className="flex flex-col gap-0.5">
        <p className="eyebrow">{marketName(m.market)}</p>
        <h2 id={`top-${m.market}`} className="text-[20px] font-bold tracking-[-0.02em] text-fg">
          {m.year}&apos;s top 5
        </h2>
        <p className="text-[13px] text-muted">Above {capFloor(m)} · from {m.priced.toLocaleString("en-US")} companies with prices</p>
      </div>
      {m.top.length === 0 ? (
        <Empty>No company cleared the bar for {m.year}.</Empty>
      ) : (
        <ol className="flex flex-col gap-2">
          {m.top.map((p, i) => (
            <PickRow key={p.company_id} p={p} rank={i + 1} />
          ))}
        </ol>
      )}
      {ty.picks !== null && ty.average !== null && ty.through ? (
        <p className="rounded-tile bg-raised px-4 py-3 text-[14px] text-muted">
          This year so far: {m.top.length === 1 ? "this one" : `these ${NUMBER[m.top.length] ?? m.top.length}`}{" "}
          <strong className={cn("num font-semibold", ty.picks >= ty.average ? "text-up" : "text-down")}>{signedPct(ty.picks)}</strong>,
          the average stock <strong className="num font-semibold text-fg">{signedPct(ty.average)}</strong>
          <span className="text-subtle"> · to {dayDate(ty.through)}</span>
        </p>
      ) : null}
    </section>
  );
}

function PickRow({ p, rank }: { p: WinnerPick; rank: number }) {
  return (
    <li>
      <Link
        href={`/company/${p.company_id}`}
        className="press tile flex items-center gap-3 p-3 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
      >
        <span
          aria-hidden="true"
          className={cn("num grid size-8 shrink-0 place-items-center rounded-full text-[14px] font-bold", rank === 1 ? "bg-pink text-on-accent" : "bg-tint-rose text-fg")}
        >
          {rank}
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[15px] font-bold">
            {p.code ?? ""} <span className="font-medium text-muted">{p.name}</span>
          </span>
          <span className="truncate text-[13px] text-subtle">
            {p.sector ?? "No sector"}
            {p.ytd !== null ? (
              <>
                {" · this year "}
                <span className={cn("num font-semibold", p.ytd >= 0 ? "text-up" : "text-down")}>{signedPct(p.ytd)}</span>
              </>
            ) : null}
          </span>
        </span>
        <span className="num shrink-0 text-[20px] font-bold tracking-[-0.02em] text-pink">{signedPct(p.ret)}</span>
        <Icon name="chevron-right" className="hidden text-subtle sm:block" />
        <LinkPending />
      </Link>
    </li>
  );
}
