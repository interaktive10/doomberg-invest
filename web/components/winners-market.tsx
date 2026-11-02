"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { LinkPending } from "@/components/link-pending";
import { shortDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { CapRangeControl } from "@/components/cap-range";
import { fullRange, rangeText, type CapRange } from "@/lib/caps";
import { capText, gainTone, marketName, signedPct, stepsOf, viewOf, type CapView, type MarketWinners } from "@/lib/winners";

const NUMBER: Record<number, string> = { 2: "two", 3: "three", 4: "four", 5: "five" };

/** One market on the Winners screen: a market-cap range, from and to (the report's steps: $1B to $500B, Rs 5,000
 * crore to Rs 5 lakh crore, no maximum) over this year's ten biggest gainers and last year's five, merged from the
 * report's buckets in that range. */
export function WinnersMarket({ m }: { m: MarketWinners }) {
  const steps = stepsOf(m);
  const [range, setRange] = useState<CapRange>(fullRange(steps));
  const band = viewOf(m, range);
  // "above $5B" or "from $5B to $50B", for the empty lists' words
  const text = steps.length > 0 ? rangeText(m.market, steps, range) : `Above ${capText(m.market, m.min_cap)}`;
  const words = text.startsWith("Above") ? text.replace("Above", "above") : `from ${text}`;
  const id = useId();
  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <h2 id={`${id}-h`} className="text-[24px] font-bold tracking-[-0.02em] text-fg">
          {marketName(m.market)}
        </h2>
        <CapRangeControl
          market={m.market}
          steps={steps}
          value={range}
          onChange={setRange}
          note={m.cap_as_of ? `Market caps as of ${shortDate(m.cap_as_of, true)}: the latest close.` : undefined}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Leaders m={m} band={band} words={words} />
        <LastYear m={m} band={band} words={words} />
      </div>
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-tile border border-dashed border-line-strong px-4 py-6 text-center text-[14px] text-muted">{children}</p>;
}

function Leaders({ m, band, words }: { m: MarketWinners; band: CapView; words: string }) {
  return (
    <div className="sheet flex min-w-0 flex-col gap-4 p-5 md:p-6">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-[18px] font-bold text-fg">{m.year + 1} so far</h3>
        <p className="text-[13px] text-muted">The biggest gainers this year: next January&apos;s list if the pattern holds.</p>
      </div>
      {band.leaders.length === 0 ? (
        <Empty>No company {words} has a price for this year yet.</Empty>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {band.leaders.map((p, n) => (
            <li key={p.company_id}>
              <Link
                href={`/company/${p.company_id}`}
                className="press tile flex items-center gap-3 px-3 py-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
              >
                <span aria-hidden="true" className="num w-6 shrink-0 text-center text-[14px] font-bold text-subtle">
                  {n + 1}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[15px] font-bold">
                    {p.code ?? ""} <span className="font-medium text-muted">{p.name}</span>
                  </span>
                  <span className="truncate text-[12px] text-subtle">
                    {p.sector ?? "No sector"}
                    {p.cap ? ` · ${capText(m.market, p.cap)}` : ""}
                  </span>
                </span>
                <span className={cn("num shrink-0 text-[20px] font-bold tracking-[-0.02em]", gainTone(p.ytd))}>{signedPct(p.ytd)}</span>
                <LinkPending />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function LastYear({ m, band, words }: { m: MarketWinners; band: CapView; words: string }) {
  const ty = band.this_year;
  const n = band.top.length;
  return (
    <div className="sheet flex min-w-0 flex-col gap-4 p-5 md:p-6">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-[18px] font-bold text-fg">{m.year}&apos;s top 5, this year</h3>
        <p className="text-[13px] text-muted">Last year&apos;s biggest gainers and how they are doing since January.</p>
      </div>
      {ty.picks !== null && ty.average !== null ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1 rounded-tile bg-raised p-3.5">
            <span className="text-[12px] font-medium text-muted">{n === 1 ? "This one" : `These ${NUMBER[n] ?? n}`}, this year</span>
            <span className={cn("num text-[28px] leading-none font-bold tracking-[-0.03em]", gainTone(ty.picks))}>{signedPct(ty.picks)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-tile bg-raised p-3.5">
            <span className="text-[12px] font-medium text-muted">The average stock this size</span>
            <span className={cn("num text-[28px] leading-none font-bold tracking-[-0.03em]", gainTone(ty.average))}>{signedPct(ty.average)}</span>
          </div>
        </div>
      ) : null}
      {n === 0 ? (
        <Empty>No company {words} cleared the bar for {m.year}.</Empty>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div aria-hidden="true" className="flex items-center gap-3 px-3 text-[11px] font-semibold tracking-[0.06em] text-subtle uppercase">
            <span className="flex-1">Company</span>
            <span className="w-16 text-right">{m.year}</span>
            <span className="w-20 text-right">This year</span>
          </div>
          <ol className="flex flex-col gap-1.5">
            {band.top.map((p) => (
              <li key={p.company_id}>
                <Link
                  href={`/company/${p.company_id}`}
                  className="press tile flex items-center gap-3 px-3 py-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[15px] font-bold">
                      {p.code ?? ""} <span className="font-medium text-muted">{p.name}</span>
                    </span>
                    <span className="truncate text-[12px] text-subtle">
                      {p.sector ?? "No sector"}
                      {p.cap ? ` · ${capText(m.market, p.cap)}` : ""}
                    </span>
                  </span>
                  <span className={cn("num w-16 shrink-0 text-right text-[14px] font-semibold", gainTone(p.ret))}>
                    <span className="sr-only">{m.year}: </span>
                    {signedPct(p.ret)}
                  </span>
                  <span className={cn("num w-20 shrink-0 text-right text-[20px] font-bold tracking-[-0.02em]", gainTone(p.ytd))}>
                    <span className="sr-only">this year: </span>
                    {signedPct(p.ytd)}
                  </span>
                  <LinkPending />
                </Link>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
