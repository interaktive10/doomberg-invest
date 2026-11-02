// Last year's winners (pipeline/reports/winners.py writes reports('winners', week); docs/SPEC_ISSUES.md 64): the body's
// shape and the plain words the Winners screen shows. Pure, so tests/winners.test.ts covers it.

import { capText, clampRange, type CapRange } from "@/lib/caps";

export { capText };

export interface WinnerPick {
  company_id: string;
  code: string | null;
  name: string;
  sector: string | null;
  ret: number;
  start: number;
  end: number;
  ytd: number | null;
  cap?: number | null;
}

export interface BacktestRow {
  year: number;
  picks: string[];
  ret: number;
  average: number;
  stocks: number;
}

export interface BacktestSummary {
  years: number;
  first: number;
  last: number;
  growth: number;
  average_growth: number;
  cagr: number;
  average_cagr: number;
  beat: number;
  best: number;
  worst: number;
}

/** One bucket of the market-cap range: companies whose cap today is in [min_cap, max_cap) (the floor's bucket also
 * holds those with no cap today), each list the bucket's own best, the average stock as a sum and a count. */
export interface CapBucket {
  min_cap: number;
  max_cap: number | null;
  top: WinnerPick[];
  leaders: Leader[];
  ytd_sum: number;
  ytd_n: number;
}

/** What the screen shows for a range: the best of its buckets merged. */
export interface CapView {
  top: WinnerPick[];
  leaders: Leader[];
  this_year: MarketWinners["this_year"];
}

export interface Leader {
  company_id: string;
  code: string | null;
  name: string;
  sector: string | null;
  ytd: number;
  start: number;
  end: number;
  cap?: number | null;
}

export interface MarketWinners {
  market: "us" | "in";
  year: number;
  currency: string;
  priced: number;
  universe: number;
  min_price: number;
  min_cap: number;
  top: WinnerPick[];
  /** this year's biggest gainers so far (reports before 2026-11-01 lack it) */
  leaders?: Leader[];
  /** the range's buckets, the floor first (reports before 2026-11-02 lack them: the screen shows the floor) */
  buckets?: CapBucket[];
  /** the date of the closes behind every row's market cap (today's caps; reports before 2026-11-02 lack it) */
  cap_as_of?: string | null;
  this_year: { through: string | null; picks: number | null; average: number | null; stocks: number };
  backtest: { rows: BacktestRow[]; summary: BacktestSummary | null } | null;
}

export interface WinnersReport {
  markets: MarketWinners[];
  as_of: string;
}

/** 0.4567 -> "+46%", -0.031 -> "-3%"; a move of 10x or more drops the decimals' noise ("+1,240%"). */
export function signedPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const p = Math.round(v * 100);
  const s = Math.abs(p).toLocaleString("en-US");
  return p > 0 ? `+${s}%` : p < 0 ? `-${s}%` : "0%";
}

/** "$1.2B" / "Rs 5,000 crore": the size floor in the market's own words. */
export function capFloor(m: Pick<MarketWinners, "market" | "min_cap">): string {
  return capText(m.market, m.min_cap);
}

/** The range's steps: each bucket's minimum (none for an older report: no range to pick). */
export function stepsOf(m: MarketWinners): number[] {
  return (m.buckets ?? []).map((b) => b.min_cap);
}

/** The lists for a range of buckets [lo, hi): last year's five and this year's ten merged best-first (a bucket's own
 * best five and ten hold the best of any union of buckets), the five's average this year and the average stock's. */
export function viewOf(m: MarketWinners, r: CapRange): CapView {
  const buckets = m.buckets ?? [];
  if (buckets.length === 0) return { top: m.top, leaders: m.leaders ?? [], this_year: m.this_year };
  const { lo, hi } = clampRange(r, buckets.length);
  const picked = buckets.slice(lo, hi);
  const top = picked.flatMap((b) => b.top).sort((a, b) => b.ret - a.ret).slice(0, 5);
  const leaders = picked.flatMap((b) => b.leaders).sort((a, b) => b.ytd - a.ytd).slice(0, 10);
  const ytds = top.map((p) => p.ytd).filter((v): v is number => v !== null && Number.isFinite(v));
  const n = picked.reduce((s, b) => s + b.ytd_n, 0);
  const sum = picked.reduce((s, b) => s + b.ytd_sum, 0);
  return {
    top,
    leaders,
    this_year: {
      through: m.this_year.through,
      picks: ytds.length ? ytds.reduce((a, b) => a + b, 0) / ytds.length : null,
      average: n > 0 ? sum / n : null,
      stocks: n,
    },
  };
}

export type Verdict = { tone: "up" | "down" | "flat"; title: string; line: string };

/** Whether buying last year's five every January beat the average stock, in one title and one line. It "worked" only
 * when it beat the average by at least two points a year AND in more than half the years (one lucky year doesn't
 * count); it "lost" when it trailed by two points or more; anything between is a wash. */
export function verdict(s: BacktestSummary): Verdict {
  const edge = s.cagr - s.average_cagr;
  const years = `${s.beat} of ${s.years} years`;
  const rates = `${signedPct(s.cagr)} a year against ${signedPct(s.average_cagr)} for the average stock`;
  if (edge >= 0.02 && s.beat * 2 > s.years) return { tone: "up", title: "It worked", line: `${rates}; ahead in ${years}.` };
  if (edge <= -0.02) return { tone: "down", title: "It didn't work", line: `${rates}; ahead in only ${years}.` };
  return { tone: "flat", title: "A wash", line: `${rates}; ahead in ${years}.` };
}

/** Gains green, losses red: the one meaning colour carries on the Winners screen. A pure helper, so the server page
 * and the client slider can both call it (a function exported from a "use client" file can't run on the server). */
export function gainTone(v: number | null | undefined): string {
  return v === null || v === undefined ? "text-subtle" : v >= 0 ? "text-up" : "text-down";
}

/** What $100 became: "$100 -> $412". */
export function grewTo(growth: number): string {
  return `$${Math.round(100 * growth).toLocaleString("en-US")}`;
}

/** Bar widths for the yearly chart: each return as a share of the largest move either way, so the longest bar fills
 * its half. */
export function barScale(rows: readonly BacktestRow[]): number {
  return Math.max(0.01, ...rows.flatMap((r) => [Math.abs(r.ret), Math.abs(r.average)]));
}

export function marketName(m: "us" | "in"): string {
  return m === "us" ? "US" : "India";
}

/** Home's Winners door: this year's biggest gainer so far, the US first; last year's top one for a report without
 * leaders (null before the first report). */
export function topWinner(r: WinnersReport | null): { code: string | null; name: string; ret: number; label: string } | null {
  for (const m of r?.markets ?? []) {
    const l = m.leaders?.[0];
    if (l) return { code: l.code, name: l.name, ret: l.ytd, label: `leads ${m.year + 1}` };
  }
  for (const m of r?.markets ?? []) {
    const p = m.top[0];
    if (p) return { code: p.code, name: p.name, ret: p.ret, label: `top of ${m.year}` };
  }
  return null;
}
