// The Signal Lab's one verdict on a signal (BRIEF §4.10.5; pipeline/lab/proposals.py verdict, the weights PR's and the
// Lab report's): works where the rule would promote its weight, hurts where it would demote it, unproven otherwise.
// It reads the out-of-sample and in-sample rows at the proposal horizon. S7-S12 read data collected only since 2026:
// "not testable yet" whatever their rows say. tests/test_web_parity.py pins these constants to config/lab.yaml and
// config/weights.yaml `lab_rules`.

export const PROPOSAL_HORIZON_MONTHS = 12;
export const PROMOTE_MIN_T_NW = 2.0;
export const DEMOTE_MAX_T_NW = -2.0;
export const NOT_TESTABLE = ["S7", "S8", "S9", "S10", "S12"] as const;

export type Verdict = "works" | "unproven" | "hurts" | "not testable yet";

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
