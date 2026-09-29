export type ChartRow = Record<string, string | number | null>;

/** A chart's y-axis range: from zero (or a little below the lowest value, when one is negative) to a little above the
 * highest, so a flat series doesn't sit on the chart's top edge. */
export function yDomain(data: readonly ChartRow[], keys: readonly string[]): [number, number] {
  const vals = data.flatMap((r) => keys.map((k) => r[k])).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (vals.length === 0) return [0, 1];
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0, ...vals);
  const pad = (hi - lo || 1) * 0.12;
  return [lo < 0 ? lo - pad : 0, hi > 0 ? hi + pad : pad];
}
