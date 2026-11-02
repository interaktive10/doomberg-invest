// The market-cap range every stock list offers (2026-11-02: "can i also have the filter/slider to have start and end
// ... on all the pages where we list the stocks ... equivalent for india as well"). The steps mirror
// pipeline/reports/winners.py CAP_STEPS (tests/test_web_parity.py); a range is a step index for the minimum and one
// for the maximum, where steps.length means no maximum. Pure, so tests/caps.test.ts covers it.

export type Market = "us" | "in";

export const CAP_STEPS: Record<Market, readonly number[]> = {
  us: [1, 2, 5, 10, 20, 50, 100, 200, 500].map((x) => x * 1e9), // $1B .. $500B
  in: [5, 10, 20, 50, 100, 200, 500].map((x) => x * 1e10), // Rs 5,000 crore .. Rs 5 lakh crore
};

/** A market cap in the market's words: "$1B", "$1.2T", "Rs 5,000 crore", "Rs 2 lakh crore". */
export function capText(market: Market, v: number): string {
  const n = (x: number) => x.toLocaleString("en-US", { maximumFractionDigits: 1 });
  if (market === "in") return v >= 1e12 ? `Rs ${n(v / 1e12)} lakh crore` : `Rs ${Math.round(v / 1e7).toLocaleString("en-US")} crore`;
  if (v >= 1e12) return `$${n(v / 1e12)}T`;
  return v >= 1e9 ? `$${n(v / 1e9)}B` : `$${Math.round(v / 1e6)}M`;
}

export interface CapRange {
  /** index of the minimum step */
  lo: number;
  /** index of the maximum step; steps.length for no maximum */
  hi: number;
}

/** The whole range: from the first step, no maximum. */
export function fullRange(steps: readonly number[]): CapRange {
  return { lo: 0, hi: steps.length };
}

/** A range kept valid: lo in [0, n-1], hi in [lo+1, n]. */
export function clampRange(r: CapRange, n: number): CapRange {
  if (n === 0) return { lo: 0, hi: 0 };
  const lo = Math.max(0, Math.min(Math.trunc(r.lo) || 0, n - 1));
  const hi = Math.max(lo + 1, Math.min(Number.isFinite(r.hi) ? Math.trunc(r.hi) : n, n));
  return { lo, hi };
}

/** "Any size", "Above $5B", "$5B to $50B", "Under $2B" (the floor is the list's own: "under" means from it). */
export function rangeText(market: Market, steps: readonly number[], r: CapRange): string {
  const { lo, hi } = clampRange(r, steps.length);
  if (steps.length === 0) return "Any size";
  if (lo === 0 && hi === steps.length) return `Above ${capText(market, steps[0]!)}`;
  if (hi === steps.length) return `Above ${capText(market, steps[lo]!)}`;
  return `${capText(market, steps[lo]!)} to ${capText(market, steps[hi]!)}`;
}

/** Whether a market cap is in the range; a company with no cap shows only at the floor (lo 0), as Winners does. */
export function inCapRange(cap: number | null | undefined, steps: readonly number[], r: CapRange): boolean {
  const { lo, hi } = clampRange(r, steps.length);
  if (steps.length === 0) return true;
  if (cap === null || cap === undefined || !Number.isFinite(cap)) return lo === 0;
  if (lo > 0 && cap < steps[lo]!) return false;
  return hi === steps.length || cap < steps[hi]!;
}

/** "?cap=2-6" <-> {lo: 2, hi: 6}; the full range writes nothing. */
export function parseRange(v: string | undefined | null, n: number): CapRange {
  const m = /^(\d{1,2})-(\d{1,2})$/.exec(v ?? "");
  return m ? clampRange({ lo: Number(m[1]), hi: Number(m[2]) }, n) : { lo: 0, hi: n };
}

export function rangeParam(r: CapRange, n: number): string | null {
  const c = clampRange(r, n);
  return c.lo === 0 && c.hi === n ? null : `${c.lo}-${c.hi}`;
}
