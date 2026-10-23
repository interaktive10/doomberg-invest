import { money } from "@/lib/format";

export type ChartRow = Record<string, string | number | null>;

/** The rows a chart draws: from the first period any of `keys` has a value to the last, so a series that starts late
 * (a TTM needs four quarters) fills its card and the card's range says what is drawn (PR 6 final review V4-1). A gap
 * inside the span stays a gap. */
export function chartSpan<T extends ChartRow>(data: readonly T[], keys: readonly string[]): T[] {
  const has = (r: T) => keys.some((k) => typeof r[k] === "number");
  const lo = data.findIndex(has);
  return lo < 0 ? [] : data.slice(lo, data.findLastIndex(has) + 1);
}

/** The series that have a value in `rows`, each with its place `i` in the card's list (its colour and dash), so a
 * series with no value at all gets neither a line nor a legend key (PR 6 final review V4-6). */
export function drawnSeries<S extends { key: string }>(rows: readonly ChartRow[], series: readonly S[]): (S & { i: number })[] {
  return series.map((s, i) => ({ ...s, i })).filter((s) => rows.some((r) => typeof r[s.key] === "number"));
}

/** A figure's minus sign as money() writes it (U+2212); a value that rounds to zero loses its sign ("-0.0%" -> "0.0%"). */
export function minus(s: string): string {
  if (!s.startsWith("-")) return s;
  return /[1-9]/.test(s) ? `−${s.slice(1)}` : s.slice(1);
}

const BIG: readonly (readonly [number, string])[] = [
  [1e12, "T"],
  [1e9, "B"],
  [1e6, "M"],
  [1e3, "K"],
  [1, ""],
];

/** A round step near `raw` (1, 2 or 5 times a power of ten). */
function niceStep(raw: number): number {
  const exp = Math.floor(Math.log10(raw));
  const f = raw / 10 ** exp;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * 10 ** exp;
}

/** A chart's y-axis: round ticks from zero (or below it, for negative values) to just above the highest value, so a flat
 * series doesn't sit on the chart's top edge and the labels read 0, 5, 10, 15 rather than 0, 6, 12, 22. */
export function yScale(data: readonly ChartRow[], keys: readonly string[], count = 4): { domain: [number, number]; ticks: number[] } {
  const vals = data.flatMap((r) => keys.map((k) => r[k])).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (vals.length === 0) return { domain: [0, 1], ticks: [0, 0.25, 0.5, 0.75, 1] };
  const top = Math.max(0, ...vals) * 1.05;
  const bottom = Math.min(0, ...vals) * 1.05;
  const step = niceStep((top - bottom || 1) / count);
  const min = Math.floor(bottom / step) * step;
  const max = Math.max(Math.ceil(top / step) * step, min + step);
  const ticks: number[] = [];
  for (let i = 0; min + i * step <= max + step / 2; i++) ticks.push(Number((min + i * step).toPrecision(12)));
  return { domain: [ticks[0]!, ticks[ticks.length - 1]!], ticks };
}

/** How a chart's figures read: money in the page's currency, a plain amount (a share count), a percentage, a multiple
 * or a count. */
export type ChartFormat = "money" | "big" | "pct" | "x" | "num";

/** A chart's figure (its headline value and each quarter in the tooltip): "$818M", "1.2B", "5.3%", "3.9×", "40". The
 * percentages keep one decimal, as the note under the chart talks in tenths of a point. A negative has a true minus
 * ("−0.4×", a net-cash company's net debt / EBITDA), and a value that would round to 1000 of a unit takes the next
 * one ("1.0M", not "1000.0K"; PR 6 final review C6, C12). */
export function chartValue(v: number, format: ChartFormat, currency?: string | null): string {
  if (!Number.isFinite(v)) return "";
  switch (format) {
    case "money":
      return money(v, currency, 3);
    case "pct":
      return minus(`${(v * 100).toFixed(1)}%`);
    case "x":
      return minus(`${v.toFixed(1)}×`);
    case "num":
      return minus(v.toFixed(0));
    case "big": {
      const a = Math.abs(v);
      let i = BIG.findIndex(([d]) => a >= d);
      if (i < 0) i = BIG.length - 1;
      if (i > 0 && Number((a / BIG[i]![0]).toFixed(1)) >= 1000) i -= 1;
      const [d, s] = BIG[i]!;
      return minus(`${(v / d).toFixed(1)}${s}`);
    }
  }
}
