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
