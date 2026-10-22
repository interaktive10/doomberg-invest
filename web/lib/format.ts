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

/** An amount as people say it: $1.83M, $447K, ₹2.5B; another currency's code goes first ("EUR 1.2M"). `digits`
 * rounds to that many significant figures instead ($818M, $1.23B: a chart's headline figure). */
export function money(v: number | null, currency?: string | null, digits?: number): string {
  if (v === null || !Number.isFinite(v)) return "n/a";
  const a = Math.abs(v);
  const [d, s, dp] = a >= 1e12 ? [1e12, "T", 2] : a >= 1e9 ? [1e9, "B", 2] : a >= 1e6 ? [1e6, "M", 2] : a >= 1e3 ? [1e3, "K", 0] : [1, "", 0];
  const cur = (currency ?? "").toUpperCase();
  const sym = cur === "USD" ? "$" : cur === "INR" ? "₹" : cur ? `${cur} ` : "";
  const shown = digits === undefined ? Number((a / d).toFixed(dp)) : Number((a / d).toPrecision(digits));
  return `${v < 0 ? "−" : ""}${sym}${shown}${s}`;
}
