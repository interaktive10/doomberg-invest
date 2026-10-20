import { detailText, FAMILY_LABEL, humanize, label } from "@/lib/labels";
import { weightOf } from "@/lib/lab";

// The Company page's "Why this score" (overhaul PR 5; BRIEF §4.8, §6): Evidence by family as pipeline/signals/
// scores.py adds it up, each fired signal's inputs in words, how long it has fired, the one-family cap in words and
// the Gap split into C1-C3. Display only: the scores row keeps the stored Evidence and Gap; this explains them. Pure,
// so tests/why.test.ts covers it.

/** config/signals.yaml `scores` (BRIEF §4.8). */
export const FAMILIES: Record<string, readonly string[]> = {
  fundamentals: ["S1", "S2", "S3", "S4", "S5", "S6"],
  behavior: ["S7", "S8"],
  text: ["S9"],
  structural: ["S10"],
  cycle: ["S12"],
};
export const MAX_SIGNALS_PER_FAMILY = 2;
export const EVIDENCE_DIVISOR = 2;
export const SINGLE_FAMILY_CAP = 55;
export const MIN_FAMILIES = 2;
export const SOFT_FLAG_PENALTY = 10;
export const GAP_METRICS = ["C1", "C2", "C3"] as const;
export const GAP_MIN_METRICS = 2;

function n(v: unknown): number | null {
  const x = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : Number.NaN;
  return Number.isFinite(x) ? x : null;
}

export interface SignalRow {
  signal_id: string;
  fired: boolean;
  strength: number | string;
  inputs: Record<string, unknown> | null;
}

export interface FamilyPart {
  family: string;
  counted: string[]; // the fired signals that count (the top 2 by weight x strength)
  beyond: string[]; // fired signals past the top 2: they add nothing
  contribution: number; // min(1, sum of the counted weight x strength)
  points: number; // what the family adds to Evidence before the cap and the red flags
}

export interface Breakdown {
  families: FamilyPart[]; // the families with a fired signal, most points first
  uncapped: number; // 100 x min(1, raw / 2)
  capped: boolean; // fewer than 2 families and above 55
  softFlags: number;
  evidence: number; // what the rules give; the stored score is the one shown
}

/** Evidence by family from the week's signal rows and the weights version the score used (its `families` W_f and
 * `signals` weight_s; 1 when it has none, as scores.py reads them). */
export function breakdown(signals: readonly SignalRow[], weights: Record<string, unknown> | null | undefined, softFlags: number): Breakdown {
  const fw = (weights?.families ?? {}) as Record<string, unknown>;
  const parts: FamilyPart[] = [];
  let raw = 0;
  for (const [family, ids] of Object.entries(FAMILIES)) {
    const fired = signals
      .filter((s) => s.fired && ids.includes(s.signal_id))
      .map((s) => ({ id: s.signal_id, v: (weightOf(weights, s.signal_id) ?? 1) * (n(s.strength) ?? 0) }))
      .sort((a, b) => b.v - a.v || a.id.localeCompare(b.id));
    if (fired.length === 0) continue;
    const top = fired.slice(0, MAX_SIGNALS_PER_FAMILY);
    const contribution = Math.min(1, top.reduce((t, x) => t + x.v, 0));
    const w = n(fw[family]) ?? 1;
    raw += w * contribution;
    parts.push({
      family,
      counted: top.map((x) => x.id),
      beyond: fired.slice(MAX_SIGNALS_PER_FAMILY).map((x) => x.id),
      contribution,
      points: (100 * w * contribution) / EVIDENCE_DIVISOR,
    });
  }
  const counting = parts.filter((p) => p.contribution > 0);
  const uncapped = 100 * Math.min(1, raw / EVIDENCE_DIVISOR);
  const capped = counting.length < MIN_FAMILIES && uncapped > SINGLE_FAMILY_CAP;
  const before = counting.length < MIN_FAMILIES ? Math.min(uncapped, SINGLE_FAMILY_CAP) : uncapped;
  return {
    families: parts.sort((a, b) => b.points - a.points || a.family.localeCompare(b.family)),
    uncapped,
    capped,
    softFlags,
    evidence: Math.max(0, before - SOFT_FLAG_PENALTY * softFlags),
  };
}

/** The one-family cap (and the soft red flags' penalty) in words. */
export function capWords(b: Breakdown): string {
  const names = b.families.filter((f) => f.contribution > 0).map((f) => label(FAMILY_LABEL, f.family));
  const flags =
    b.softFlags === 0
      ? ""
      : ` ${b.softFlags === 1 ? "One soft red flag" : `${b.softFlags} soft red flags`} subtract${b.softFlags === 1 ? "s" : ""} ${SOFT_FLAG_PENALTY * b.softFlags}.`;
  if (names.length === 0) return `No signal fired, so Evidence is 0.${flags}`;
  if (names.length >= MIN_FAMILIES)
    return `${names.length} families fired (${names.join(", ")}), so the one-family cap at ${SINGLE_FAMILY_CAP} does not apply.${flags}`;
  const one = `Only one family fired (${names[0]}), so Evidence is capped at ${SINGLE_FAMILY_CAP}`;
  return b.capped
    ? `${one}: it would be ${b.uncapped.toFixed(0)} with a second family. Evidence of 60 or more needs two.${flags}`
    : `${one}; at ${b.uncapped.toFixed(0)} the cap does not bind yet.${flags}`;
}

/** The first week of the signal's current unbroken run of fired weeks, ending at `week`: walking back through the
 * company's scored weeks, a scored week where it did not fire ends the run. null when it did not fire in `week`. */
export function firingSince(week: string, scoredWeeks: readonly string[], firedWeeks: ReadonlySet<string> | readonly string[]): string | null {
  const fired = firedWeeks instanceof Set ? firedWeeks : new Set(firedWeeks as readonly string[]);
  if (!fired.has(week)) return null;
  let since = week;
  for (const w of [...new Set(scoredWeeks)].filter((x) => x < week).sort().reverse()) {
    if (!fired.has(w)) break;
    since = w;
  }
  return since;
}

type Kind = "pct" | "pp" | "x" | "big" | "num" | "int" | "text";

// The keys pipeline/signals/s*.py, redflags.py, context.py and reverse_dcf.py write into inputs (BRIEF §4.6, §4.7).
const INPUT_LABEL: Record<string, [label: string, kind: Kind]> = {
  source: ["Order book from", "text"],
  gaps: ["Order-book growth minus revenue growth, last 2 quarters", "pct"],
  coverage: ["Order book / TTM revenue", "x"],
  coverage_year_ago: ["Order book / TTM revenue a year ago", "x"],
  nopat: ["NOPAT (TTM)", "big"],
  ic: ["Invested capital", "big"],
  d_ic: ["Change in invested capital", "big"],
  roic: ["ROIC", "pct"],
  revenue_yoy: ["Quarterly revenue growth (YoY)", "pct"],
  opm: ["Operating margin (TTM)", "pct"],
  opm_year_ago: ["Operating margin a year ago", "pct"],
  g_opex: ["Opex growth (TTM)", "pct"],
  g_revenue: ["Revenue growth (TTM)", "pct"],
  ccr: ["Cash conversion (CFO / net income)", "x"],
  ccr_year_ago: ["Cash conversion a year ago", "x"],
  sloan: ["Sloan accruals", "pct"],
  sloan_year_ago: ["Sloan accruals a year ago", "pct"],
  ttm_cfo: ["Operating cash flow (TTM)", "big"],
  ttm_cfo_year_ago: ["Operating cash flow a year ago", "big"],
  ttm_net_income: ["Net income (TTM)", "big"],
  ttm_net_income_year_ago: ["Net income a year ago", "big"],
  shares_source: ["Share count from", "text"],
  share_change_yoy: ["Share count change (YoY)", "pct"],
  past_max: ["Highest ND/EBITDA, 4-8 quarters ago", "x"],
  current: ["ND/EBITDA now", "x"],
  interest_coverage: ["Interest coverage", "x"],
  insiders: ["Insiders buying", "int"],
  total_usd: ["Bought (USD)", "big"],
  buyers: ["Buyers", "text"],
  promoter_buyers: ["Promoter buyers", "int"],
  total_inr: ["Bought (INR)", "big"],
  holders: ["13F holders, by quarter", "int"],
  qoq: ["Holder growth (QoQ)", "pct"],
  pct_in_size_decile: ["Holder-count percentile in its size decile", "num"],
  fii_dii_pct: ["FII + DII holding (%)", "num"],
  rise_pp: ["Rise over 2 quarters (pp)", "pp"],
  count: ["Verified facts", "int"],
  facts: ["Facts", "text"],
  events: ["Events", "text"],
  holdco: ["Listed holding company", "text"],
  sector: ["Sector", "text"],
  capex_da_medians: ["Sector median capex / D&A, last 3 years", "x"],
  revenue_yoy_medians: ["Sector median revenue growth", "pct"],
  tightness_facts: ["Tightness facts in the sector", "int"],
  company_fires: ["Company fires", "text"],
  cfo_to_ni: ["CFO / net income", "x"],
  receivables_growth: ["Receivables growth", "pct"],
  revenue_growth: ["Revenue growth", "pct"],
  gap_pp: ["Receivables minus revenue growth (pp)", "pp"],
  revenue_basis: ["Revenue basis", "text"],
  text: ["Verified text", "text"],
  acquisitions: ["Acquisitions", "text"],
  splits: ["Splits", "text"],
  pledged_pct_of_promoter: ["Pledged share of the promoter holding (%)", "num"],
  surveillance: ["ASM/GSM", "text"],
  rpt_revenue_pct: ["Related-party revenue (%)", "num"],
  hits: ["Hits", "text"],
  net_debt: ["Net debt, last 4 quarters", "big"],
  fcf: ["Free cash flow, last 4 quarters", "big"],
  s1: ["S1 fires", "text"],
  weeks: ["Weeks of history", "int"],
  ev_sales: ["EV / sales", "x"],
  ev_ebit: ["EV / EBIT", "x"],
  pct_ev_sales: ["EV / sales percentile vs its own history", "num"],
  pct_ev_ebit: ["EV / EBIT percentile vs its own history", "num"],
  return_52w: ["52-week return", "pct"],
  population: ["Comparison group", "int"],
  min_population: ["Smallest group it reads", "int"],
  already_ran: ["Already ran (90th percentile or more)", "text"],
  missing: ["Missing inputs", "text"],
};

/** "nopat_12q" -> "NOPAT (TTM) 12 quarters ago". */
function lagged(key: string): [string, Kind] | undefined {
  const m = /^([a-z_]+?)_(\d+)q$/.exec(key);
  const base = m?.[1] ? INPUT_LABEL[m[1]] : undefined;
  return base && m ? [`${base[0]} ${m[2]} quarters ago`, base[1]] : undefined;
}

function one(v: unknown, kind: Kind): string {
  if (v === null || v === undefined) return "n/a";
  if (typeof v === "boolean") return v ? "yes" : "no";
  const x = n(v);
  if (x === null || kind === "text") return typeof v === "object" ? detailText(v) : String(v);
  switch (kind) {
    case "pct":
      return `${(x * 100).toFixed(1)}%`;
    case "pp":
      return `${x.toFixed(1)} pp`;
    case "x":
      return `${x.toFixed(2)}x`;
    case "big": {
      const a = Math.abs(x);
      const [d, s] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
      return `${(x / d).toFixed(2)}${s}`;
    }
    case "int":
      return Math.round(x).toLocaleString("en-US");
    case "num":
      return x.toFixed(1);
  }
}

function value(v: unknown, kind: Kind): string {
  if (Array.isArray(v) && v.every((x) => x === null || typeof x !== "object")) return v.length === 0 ? "none" : v.map((x) => one(x, kind)).join(", ");
  return one(v, kind);
}

export interface InputRow {
  key: string;
  label: string;
  value: string;
}

/** A signal's, red flag's or context metric's stored inputs as rows: the keys it knows by name in a fixed order and
 * unit, then any other key raw (key: value as stored). `skip` leaves keys out (the status, a score shown already). */
export function inputRows(inputs: Record<string, unknown> | null | undefined, skip: readonly string[] = []): InputRow[] {
  const entries = Object.entries(inputs ?? {}).filter(([k]) => !skip.includes(k));
  const order = Object.keys(INPUT_LABEL);
  const known = entries
    .map(([k, v]) => ({ k, v, def: INPUT_LABEL[k] ?? lagged(k) }))
    .filter((x) => x.def !== undefined)
    .sort((a, b) => (order.indexOf(a.k) < 0 ? order.length : order.indexOf(a.k)) - (order.indexOf(b.k) < 0 ? order.length : order.indexOf(b.k)) || a.k.localeCompare(b.k))
    .map(({ k, v, def }) => ({ key: k, label: def![0], value: value(v, def![1]) }));
  const rest = entries
    .filter(([k]) => INPUT_LABEL[k] === undefined && lagged(k) === undefined)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => ({ key: k, label: k, value: v !== null && typeof v === "object" ? JSON.stringify(v) : String(v) }));
  return [...known, ...rest];
}

export interface ContextRow {
  metric_id: string;
  value: number | string | null;
  pct: number | string | null;
  inputs: Record<string, unknown> | null;
}

export interface GapPart {
  id: (typeof GAP_METRICS)[number];
  score: number | null;
  missing: string | null; // why there is no score: the inputs it lacked, or no row this week
  row: ContextRow | null;
}

/** The Gap as its parts: C1-C3 with each one's score (inputs.score, what Gap averages) or why it has none, and the
 * mean of those it has (null with fewer than 2, the bucket's `none`). */
export function gapParts(context: readonly ContextRow[]): { parts: GapPart[]; mean: number | null } {
  const parts = GAP_METRICS.map((id): GapPart => {
    const row = context.find((c) => c.metric_id === id) ?? null;
    const score = n(row?.inputs?.score);
    const lacked = row?.inputs?.missing;
    const missing =
      score !== null
        ? null
        : row === null
          ? "not computed this week"
          : Array.isArray(lacked) && lacked.length > 0
            ? `missing ${lacked.map((x) => humanize(String(x)).toLowerCase()).join(", ")}`
            : "no score";
    return { id, score, missing, row };
  });
  const known = parts.map((p) => p.score).filter((s): s is number => s !== null);
  return { parts, mean: known.length < GAP_MIN_METRICS ? null : known.reduce((t, s) => t + s, 0) / known.length };
}
