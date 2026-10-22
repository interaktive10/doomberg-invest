import { money } from "@/lib/format";

export type ChartRow = Record<string, string | number | null>;

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
 * percentages keep one decimal, as the note under the chart talks in tenths of a point. */
export function chartValue(v: number, format: ChartFormat, currency?: string | null): string {
  if (!Number.isFinite(v)) return "";
  switch (format) {
    case "money":
      return money(v, currency, 3);
    case "pct":
      return `${(v * 100).toFixed(1)}%`;
    case "x":
      return `${v.toFixed(1)}×`;
    case "num":
      return v.toFixed(0);
    case "big": {
      const a = Math.abs(v);
      const [d, s] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
      return `${(v / d).toFixed(1)}${s}`;
    }
  }
}
