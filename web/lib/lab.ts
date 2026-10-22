// The Signal Lab's one verdict on a signal (BRIEF §4.10.5; pipeline/lab/proposals.py verdict, the weights PR's and the
// Lab report's): works where the rule would promote its weight, hurts where it would demote it, unproven otherwise.
// It reads the out-of-sample and in-sample rows at the proposal horizon. S7-S12 read data collected only since 2026:
// "not testable yet" whatever their rows say. tests/test_web_parity.py pins these constants to config/lab.yaml and
// config/weights.yaml `lab_rules`.

export const PROPOSAL_HORIZON_MONTHS = 12;
export const PROMOTE_MIN_T_NW = 2.0;
export const DEMOTE_MAX_T_NW = -2.0;
export const NOT_TESTABLE = ["S7", "S8", "S9", "S10", "S12"] as const;
/** The weight a signal that works is promoted to: the top of the Lab screen's weight bars. */
export const PROMOTE_WEIGHT = 1.5;

export type Verdict = "works" | "unproven" | "hurts" | "not testable yet";

/** The verdicts in the order the Lab screen counts them. */
export const VERDICTS: readonly Verdict[] = ["works", "unproven", "hurts", "not testable yet"];

export interface LabRow {
  signal_id: string;
  horizon_m: number;
  period: "in_sample" | "out_of_sample";
  excess_mean: number | string | null;
  t_nw: number | string | null;
}

function n(v: number | string | null): number | null {
  const x = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(x) ? x : null;
}

/** The verdict from one Lab run's rows (lib/data.ts labResults). */
export function verdict(signal: string, rows: readonly LabRow[]): Verdict {
  if ((NOT_TESTABLE as readonly string[]).includes(signal)) return "not testable yet";
  const at = (period: LabRow["period"]) => rows.find((r) => r.signal_id === signal && r.horizon_m === PROPOSAL_HORIZON_MONTHS && r.period === period);
  const oos = at("out_of_sample");
  const mean = oos ? n(oos.excess_mean) : null;
  const t = oos ? n(oos.t_nw) : null;
  if (mean === null || t === null) return "unproven"; // no out-of-sample events
  if (mean > 0 && t >= PROMOTE_MIN_T_NW) {
    const ins = at("in_sample");
    const insMean = ins ? n(ins.excess_mean) : null;
    return insMean !== null && insMean > 0 ? "works" : "unproven";
  }
  return mean < 0 && t <= DEMOTE_MAX_T_NW ? "hurts" : "unproven";
}

/** The weight a weights_versions row gives a signal: its `signals` (S*) or `legacy` (L*) entry; null when it has none. */
export function weightOf(weights: Record<string, unknown> | null | undefined, signal: string): number | null {
  for (const section of ["signals", "legacy"]) {
    const s = weights?.[section];
    if (typeof s === "object" && s !== null && signal in s) return n((s as Record<string, number | string | null>)[signal] ?? null);
  }
  return null;
}

/** A lab_prices runs row: pipeline/lab/price_history.py writes the download's stats (Outcome.stats). */
export interface LabPricesRun {
  started_at: string;
  status: string;
  error: string | null;
  stats: { status?: string; tickers?: number; ok?: number; no_such_symbol?: number; error?: number; pending?: number };
}

/** The Lab page's progress line for the price download (the latest lab_prices runs row). */
export function downloadLine(run: LabPricesRun | null): string {
  if (run === null) return "Price download: not started yet (lab-prices.yml downloads the Twelve Data month-end prices first).";
  const s = run.stats;
  const total = Number(s.tickers ?? 0);
  const settled = Math.max(0, total - Number(s.pending ?? 0));
  const fmt = (x: number | undefined) => Number(x ?? 0).toLocaleString("en-US");
  const tally = `${fmt(settled)} of ${fmt(total)} tickers settled (${fmt(s.ok)} ok, ${fmt(s.no_such_symbol)} no such symbol, ${fmt(s.error)} error)`;
  const when = `last run ${run.started_at.slice(0, 10)}`;
  if (s.status === "complete") return `Price download: complete, ${tally}; ${when}.`;
  if (s.status === "blocked") return `Price download: blocked${run.error ? `: ${run.error}` : ""}; ${when}.`;
  return `Price download: ${tally}, ${fmt(s.pending)} to go; ${when}.`;
}

// ---------------------------------------------------------------- the Lab screen's visuals (overhaul PR 6)

export type DownloadState = "not started" | "running" | "complete" | "blocked";

/** The price download as numbers for its meter: tickers settled of the total (and the share, 0-100), how they
 * settled, and the run's day. A missing or negative count reads as 0. */
export interface DownloadProgress {
  state: DownloadState;
  total: number;
  settled: number;
  pending: number;
  ok: number;
  missing: number;
  failed: number;
  pct: number;
  day: string | null;
  error: string | null;
}

export function downloadProgress(run: LabPricesRun | null): DownloadProgress {
  const count = (x: number | undefined) => {
    const v = Number(x ?? 0);
    return Number.isFinite(v) && v > 0 ? v : 0;
  };
  if (run === null) return { state: "not started", total: 0, settled: 0, pending: 0, ok: 0, missing: 0, failed: 0, pct: 0, day: null, error: null };
  const s = run.stats;
  const total = count(s.tickers);
  const pending = count(s.pending);
  const settled = Math.max(0, total - pending);
  const state: DownloadState = s.status === "complete" ? "complete" : s.status === "blocked" ? "blocked" : "running";
  return {
    state,
    total,
    settled,
    pending,
    ok: count(s.ok),
    missing: count(s.no_such_symbol),
    failed: count(s.error),
    pct: total > 0 ? Number(Math.min(100, (settled / total) * 100).toFixed(1)) : 0,
    day: run.started_at.slice(0, 10),
    error: state === "blocked" ? run.error : null,
  };
}

/** How many signals have each verdict. */
export function tally(verdicts: readonly Verdict[]): Record<Verdict, number> {
  const out: Record<Verdict, number> = { works: 0, unproven: 0, hurts: 0, "not testable yet": 0 };
  for (const v of verdicts) out[v] += 1;
  return out;
}

/** The Lab screen's one line under its title, the answer first. `ran`: a Lab run has written results. */
export function labHeadline(t: Record<Verdict, number>, ran: boolean, download: DownloadState): string {
  if (!ran) return download === "complete" ? "The prices are in: the first Lab run is next." : "No Lab run yet: the price download comes first.";
  const testable = t.works + t.unproven + t.hurts;
  if (testable === 0) return "Nothing the Lab can test yet.";
  if (t.works > 0) return `${t.works} of ${testable} testable signals ${t.works === 1 ? "beats" : "beat"} the market out of sample.`;
  if (t.hurts > 0) return `Nothing beats the market yet, and ${t.hurts} ${t.hurts === 1 ? "signal hurts" : "signals hurt"}.`;
  return "Nothing has proven itself yet: every testable signal is unproven.";
}

/** A signal's headline result: the out-of-sample row at the proposal horizon that its verdict reads. `share` is its
 * mean's size against the largest one shown (0-100), the length of its bar. */
export interface Headline {
  signal: string;
  mean: number;
  t: number | null;
  share: number;
}

/** Each signal's headline result, best first; a signal with no such row (or no mean in it) is left out. */
export function headlines(rows: readonly LabRow[]): Headline[] {
  const seen = new Map<string, { mean: number; t: number | null }>();
  for (const r of rows) {
    if (seen.has(r.signal_id) || r.horizon_m !== PROPOSAL_HORIZON_MONTHS || r.period !== "out_of_sample") continue;
    const mean = n(r.excess_mean);
    if (mean !== null) seen.set(r.signal_id, { mean, t: n(r.t_nw) });
  }
  const top = Math.max(0, ...[...seen.values()].map((h) => Math.abs(h.mean)));
  return [...seen.entries()]
    .map(([signal, h]) => ({ signal, ...h, share: top > 0 ? Number(((Math.abs(h.mean) / top) * 100).toFixed(1)) : 0 }))
    .sort((a, b) => b.mean - a.mean || a.signal.localeCompare(b.signal, "en", { numeric: true }));
}

const DECILE = /^(EVIDENCE|GAP)_D(\d+)$/;

/** Whether a Lab row is a score decile (EVIDENCE_D1 ... GAP_D10) rather than a signal. */
export function isDecile(id: string): boolean {
  return DECILE.test(id);
}

/** A score's deciles 1 to `count` out of sample at the proposal horizon: each one's mean excess return, null where
 * there is no row. */
export function decileMeans(rows: readonly LabRow[], score: "EVIDENCE" | "GAP", count = 10): (number | null)[] {
  const out: (number | null)[] = Array.from({ length: count }, () => null);
  for (const r of rows) {
    const m = DECILE.exec(r.signal_id);
    if (!m || m[1] !== score || r.horizon_m !== PROPOSAL_HORIZON_MONTHS || r.period !== "out_of_sample") continue;
    const i = Number(m[2]) - 1;
    if (i >= 0 && i < count && out[i] === null) out[i] = n(r.excess_mean);
  }
  return out;
}

/** A column chart's shape in percent of its box: where the zero line sits (from the top), and for each value the
 * column's top and height. Zero is at the bottom when nothing is negative, at the middle when both signs show, at the
 * top when nothing is positive; a null is a column of height 0 on the zero line. */
export function columnGeometry(values: readonly (number | null)[]): { zero: number; bars: { top: number; height: number; sign: -1 | 0 | 1 }[] } {
  const nums = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const hi = Math.max(0, ...nums);
  const lo = Math.min(0, ...nums);
  const span = hi - lo || 1;
  const zero = Number(((hi / span) * 100).toFixed(1));
  const bars = values.map((v) => {
    if (v === null || !Number.isFinite(v) || v === 0) return { top: zero, height: 0, sign: 0 as const };
    const h = Number(((Math.abs(v) / span) * 100).toFixed(1));
    return v > 0 ? { top: Math.max(0, Number((zero - h).toFixed(1))), height: h, sign: 1 as const } : { top: zero, height: h, sign: -1 as const };
  });
  return { zero, bars };
}
