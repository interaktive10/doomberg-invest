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

export function code(c: { market: string; ticker: string | null; nse_symbol: string | null }): string {
  return (c.market === "us" ? c.ticker : c.nse_symbol) ?? c.market.toUpperCase();
}
