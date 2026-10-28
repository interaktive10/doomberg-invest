export function num(v: number | string | null | undefined, digits = 1): string {
  if (v === null || v === undefined || v === "") return "n/a";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : "n/a";
}

export function pct(v: number | string | null | undefined, digits = 1): string {
  if (v === null || v === undefined || v === "") return "n/a";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "n/a";
}

/** 1234567890 -> "1.23B"; money in the company's currency (no symbol: US and India both appear). */
export function big(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "n/a";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "n/a";
  const a = Math.abs(n);
  const [d, s] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  return `${(n / d).toFixed(2)}${s}`;
}

/** A metric's value in a table, at a precision that suits its size: 0.2400 (a ratio), 82.0 (a score), 1.22B (an
 * amount). */
export function measure(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "n/a";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "n/a";
  const a = Math.abs(n);
  return a >= 1e4 ? big(n) : a >= 10 ? n.toFixed(1) : n.toFixed(4);
}

export function code(c: { market: string; ticker: string | null; nse_symbol: string | null }): string {
  return (c.market === "us" ? c.ticker : c.nse_symbol) ?? c.market.toUpperCase();
}

const TIERS: readonly (readonly [number, string, number])[] = [
  [1e12, "T", 2],
  [1e9, "B", 2],
  [1e6, "M", 2],
  [1e3, "K", 0],
  [1, "", 0],
];

const LAKH = 1e5;
const CRORE = 1e7;
const LAKH_CRORE = 1e12;
const EN_IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

/** Rupees as Indian investors say them (docs/SPEC_ISSUES.md 56): ₹2.65 lakh cr, ₹26,458 cr, ₹45.3 cr, ₹3.4 lakh, ₹450,
 * with Indian digit grouping (₹2,64,573 cr never happens: that is ₹2.65 lakh cr). `digits` rounds to that many
 * significant figures instead, as money() does. */
function rupees(v: number, digits?: number): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  const fix = (x: number, dp: number) => (digits === undefined ? Number(x.toFixed(dp)) : Number(x.toPrecision(digits)));
  const crore = fix(a / CRORE, a / CRORE >= 100 ? 0 : 1);
  if (a >= LAKH_CRORE || (a >= CRORE && crore >= 1e5)) return `${sign}₹${EN_IN.format(fix(a / LAKH_CRORE, 2))} lakh cr`;
  if (a >= CRORE) return `${sign}₹${EN_IN.format(crore)} cr`;
  const lakh = fix(a / LAKH, 1);
  if (a >= LAKH) return lakh >= 100 ? `${sign}₹${EN_IN.format(fix(a / CRORE, 1))} cr` : `${sign}₹${EN_IN.format(lakh)} lakh`;
  return `${sign}₹${EN_IN.format(fix(a, 0))}`;
}

/** An amount as people say it: $1.83M, $447K; rupees in crore (rupees()); another currency's code goes first ("EUR
 * 1.2M"). `digits` rounds to that many significant figures instead ($818M, $1.23B: a chart's headline figure). The unit
 * is chosen after rounding, so $999.7K reads "$1M", not "$1000K" (PR 6 final review C6). */
export function money(v: number | null, currency?: string | null, digits?: number): string {
  if (v === null || !Number.isFinite(v)) return "n/a";
  if ((currency ?? "").toUpperCase() === "INR") return rupees(v, digits);
  const a = Math.abs(v);
  const round = (k: number) => {
    const [d, , dp] = TIERS[k]!;
    return digits === undefined ? Number((a / d).toFixed(dp)) : Number((a / d).toPrecision(digits));
  };
  let i = TIERS.findIndex(([d]) => a >= d);
  if (i < 0) i = TIERS.length - 1;
  if (i > 0 && round(i) >= 1000) i -= 1;
  const cur = (currency ?? "").toUpperCase();
  const sym = cur === "USD" ? "$" : cur ? `${cur} ` : "";
  return `${v < 0 ? "−" : ""}${sym}${round(i)}${TIERS[i]![1]}`;
}

/** A text fact's money unit: facts store any amount as `usd` (or `usd_per_year`) with its currency beside it, so an
 * Indian company's are rupees (docs/SPEC_ISSUES.md 31, 58). */
export function isMoney(unit: string): boolean {
  return unit === "usd" || unit === "usd_per_year";
}
