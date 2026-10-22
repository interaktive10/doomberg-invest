// The maths behind the shared visuals (overhaul PR 6): score rings, sparklines, meters and split bars, and ticker
// tiles. Pure, so tests/visual.test.ts covers it; components/score-ring.tsx, sparkline.tsx, meter.tsx and
// ticker-tile.tsx draw with it.

/** v clamped to [lo, hi]; a non-finite v is lo. */
export function clamp(v: number, lo: number, hi: number): number {
  return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : lo;
}

/** A score ring of radius r: its circumference, the arc for `value` (0-100, clamped) and the number it shows (rounded;
 * null when there is no score). The arc is drawn as stroke-dasharray `${length} ${circumference}`. */
export function ringGeometry(value: number | null, r: number): { circumference: number; length: number; shown: number | null } {
  const circumference = Number((2 * Math.PI * r).toFixed(2));
  if (value === null || !Number.isFinite(value)) return { circumference, length: 0, shown: null };
  const v = clamp(value, 0, 100);
  return { circumference, length: Number(((circumference * v) / 100).toFixed(2)), shown: Math.round(v) };
}

/** A bar's fill in percent of its track: value / max, clamped to 0-100 and rounded to 0.1. */
export function meterPct(value: number, max = 100): number {
  if (!(max > 0)) return 0;
  return Number(clamp((value / max) * 100, 0, 100).toFixed(1));
}

/** Segment widths (percent) of a split bar whose parts add up against `max`: negative parts count as 0, and when the
 * parts add up to more than max they are scaled down to fill the bar exactly. */
export function splitWidths(values: readonly number[], max = 100): number[] {
  const parts = values.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = parts.reduce((a, b) => a + b, 0);
  const scale = total > max ? max / total : 1;
  return parts.map((v) => (max > 0 ? Number(((v * scale * 100) / max).toFixed(1)) : 0));
}

export interface SparkRun {
  /** polyline points: "x,y x,y ..." (a lone value repeats its point, so a round cap draws it as a dot) */
  line: string;
  /** polygon points: the run closed down (or up) to the zero line */
  area: string;
  /** a stretch of one value: draw it as a dot */
  dot: boolean;
}

/** A sparkline's shape in a width x height box with `pad` above and below: the y of the zero line (zero is always in
 * range, so a fall below it shows) and one run per stretch of consecutive values (a null breaks the line). Points are
 * spread evenly over the width by position, so a missing quarter leaves its gap. */
export function sparkGeometry(
  values: readonly (number | null | undefined)[],
  width: number,
  height: number,
  pad = 6,
): { zero: number; runs: SparkRun[] } {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const lo = Math.min(0, ...nums);
  const hi = Math.max(0, ...nums);
  const span = hi - lo || 1;
  const y = (v: number) => Number((pad + (height - 2 * pad) * (1 - (v - lo) / span)).toFixed(1));
  const x = (i: number) => Number((values.length > 1 ? (width * i) / (values.length - 1) : width / 2).toFixed(1));
  const zero = y(0);
  const runs: SparkRun[] = [];
  let run: [number, number][] = [];
  const flush = () => {
    if (run.length > 0) {
      const pts = run.map(([px, py]) => `${px},${py}`).join(" ");
      const dot = run.length === 1;
      runs.push({ line: dot ? `${pts} ${pts}` : pts, area: `${run[0]![0]},${zero} ${pts} ${run[run.length - 1]![0]},${zero}`, dot });
    }
    run = [];
  };
  values.forEach((v, i) => {
    if (typeof v === "number" && Number.isFinite(v)) run.push([x(i), y(v)]);
    else flush();
  });
  flush();
  return { zero, runs };
}

export type Tint = "sky" | "sage" | "sand" | "clay";
const TINTS: readonly Tint[] = ["sky", "sage", "sand", "clay"];

/** A ticker tile's tint: the same company always gets the same one. */
export function tintFor(key: string): Tint {
  let h = 0;
  for (const ch of key.toUpperCase()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TINTS[h % TINTS.length]!;
}

/** The letters a ticker tile shows: the code in capitals without an exchange suffix (".NS", ".BO"; a one-letter share
 * class such as BRK.B stays), at most 5 characters. */
export function tileText(ticker: string): string {
  return ticker.trim().toUpperCase().replace(/\.[A-Z]{2,}$/, "").slice(0, 5);
}

/** What a row of evidence dots says to a screen reader: "2 kinds of evidence: business, insiders". */
export function kindsLabel(words: readonly string[]): string {
  if (words.length === 0) return "No kind of evidence yet";
  return `${words.length} ${words.length === 1 ? "kind" : "kinds"} of evidence: ${words.join(", ")}`;
}
