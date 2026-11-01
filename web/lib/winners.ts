// Last year's winners (pipeline/reports/winners.py writes reports('winners', week); docs/SPEC_ISSUES.md 64): the body's
// shape and the plain words the Winners screen shows. Pure, so tests/winners.test.ts covers it.

export interface WinnerPick {
  company_id: string;
  code: string | null;
  name: string;
  sector: string | null;
  ret: number;
  start: number;
  end: number;
  ytd: number | null;
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

export interface MarketWinners {
  market: "us" | "in";
  year: number;
  currency: string;
  priced: number;
  universe: number;
  min_price: number;
  min_cap: number;
  top: WinnerPick[];
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
  if (m.market === "in") return `Rs ${Math.round(m.min_cap / 1e7).toLocaleString("en-US")} crore`;
  return m.min_cap >= 1e9 ? `$${(m.min_cap / 1e9).toLocaleString("en-US", { maximumFractionDigits: 1 })}B` : `$${Math.round(m.min_cap / 1e6)}M`;
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

/** Home's Winners door: last year's biggest gainer, the US first (null before the first report). */
export function topWinner(r: WinnersReport | null): (WinnerPick & { year: number }) | null {
  for (const m of r?.markets ?? []) {
    const p = m.top[0];
    if (p) return { ...p, year: m.year };
  }
  return null;
}
