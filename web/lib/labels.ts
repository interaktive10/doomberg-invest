import type { FactRow } from "@/lib/data";
import { big, isMoney, measure, money, num } from "@/lib/format";

// Display names for the ids the pipeline stores (BRIEF §1.4 signals, §1.5 red flags, §1.6 context, §4.7 reverse DCF,
// the kill-criteria metrics). Display only: forms, URLs and the database keep the ids.

/** snake_case or kebab-case id -> "Sentence case" ("open_market_buy" -> "Open market buy"). */
export function humanize(id: string | null | undefined): string {
  if (id === null || id === undefined) return "";
  const s = id.replace(/[_-]+/g, " ").trim();
  return s === "" ? "" : s[0]!.toUpperCase() + s.slice(1);
}

export const BUCKET_LABEL: Record<string, string> = {
  candidate: "Candidate",
  early: "Early",
  watch: "Watch",
  priced_in: "Priced-in",
  excluded: "Excluded",
  none: "No bucket",
};

export const FAMILY_LABEL: Record<string, string> = {
  fundamentals: "Fundamentals",
  behavior: "Behavior",
  text: "Text",
  structural: "Structural",
  cycle: "Cycle",
};

/** BRIEF §1.4. */
export const SIGNAL_NAME: Record<string, string> = {
  S1: "Order-book acceleration",
  S2: "Incremental-ROIC inflection",
  S3: "Operating-leverage onset",
  S4: "Earnings-quality inflection",
  S5: "Capital discipline",
  S6: "De-risking complete",
  S7: "Insider conviction",
  S8: "Discovery",
  S9: "Verified text facts",
  S10: "Special situations",
  S12: "Cycle position",
};

/** The same signals in everyday words, for the Candidates cards ("why it's here"). */
export const SIGNAL_PLAIN: Record<string, string> = {
  S1: "Order book growing faster than sales",
  S2: "Returns on new investment rising",
  S3: "Margins widening as sales grow",
  S4: "Cash flow rising ahead of profits",
  S5: "Buying back shares from free cash flow",
  S6: "Debt paid down",
  S7: "Insiders buying shares",
  S8: "More funds starting to own it",
  S9: "Verified wins in its filings",
  S10: "Spin-off or special situation",
  S12: "Industry cycle turning up",
};

/** Each signal's short name, the one every screen shows (the Company page's Why rows, the Lab, Home's board, a card's
 * citation chips); the code stays in its title or details. */
export const SIGNAL_SHORT: Record<string, string> = {
  S1: "Order book",
  S2: "Returns on new capital",
  S3: "Operating leverage",
  S4: "Earnings quality",
  S5: "Capital discipline",
  S6: "Debt paid down",
  S7: "Insider buying",
  S8: "Funds discovering it",
  S9: "Verified wins in filings",
  S10: "Special situation",
  S12: "Cycle turning",
};

export function signalShort(id: string): string {
  return SIGNAL_SHORT[id] ?? SIGNAL_NAME[id] ?? id;
}

/** BRIEF §1.5. */
export const RED_FLAG_NAME: Record<string, string> = {
  R1: "Accruals high or cash conversion weak",
  R2: "Receivables outgrowing revenue",
  R3: "Auditor change, late filing or going-concern language",
  R4: "Share count up 10% without an acquisition",
  R5: "Promoter pledge, ASM/GSM or related-party revenue",
  R6: "Negative FCF with net debt rising",
};

/** BRIEF §1.6. */
export const CONTEXT_NAME: Record<string, string> = {
  C1: "Valuation percentile vs its own history",
  C2: "Expectations gap (evidence growth minus reverse-DCF implied growth)",
  C3: "Run-up: 12-month return percentile",
};

/** The Gap's parts by their short names (the codes stay in titles and details). */
export const GAP_SHORT: Record<string, string> = { C1: "Cheap vs its past", C2: "Growth test", C3: "Price move" };

export const ACTION_LABEL: Record<string, string> = {
  note: "Note",
  start_position: "Start position",
  add: "Add",
  trim: "Trim",
  exit: "Exit",
  review: "Review",
};

type MetricUnit = "money" | "ratio" | "count" | "percent" | "score" | "strength";

/** The kill-criteria metrics (pipeline/thesis/evidence_pack.py KILL_METRICS; tests/test_web_parity.py pins the keys),
 * named to sit in a sentence, with the unit their values are in. A card's metric id is "m:<key>" or "m:signal:S<n>". */
export const METRIC_LABEL: Record<string, { label: string; unit: MetricUnit }> = {
  revenue_ttm: { label: "trailing-twelve-month revenue", unit: "money" },
  revenue_ttm_yoy: { label: "TTM revenue growth over the TTM a year earlier", unit: "ratio" },
  revenue_q_yoy: { label: "the latest quarter's revenue growth over the same quarter a year earlier", unit: "ratio" },
  op_margin_ttm: { label: "the TTM operating margin", unit: "ratio" },
  roic: { label: "ROIC (TTM NOPAT over mean invested capital)", unit: "ratio" },
  fcf_ttm: { label: "TTM free cash flow (operating cash flow minus capex)", unit: "money" },
  net_debt: { label: "net debt (total debt minus cash)", unit: "money" },
  rpo: { label: "remaining performance obligations (RPO)", unit: "money" },
  rpo_yoy: { label: "RPO growth over a year earlier", unit: "ratio" },
  shares_yoy: { label: "the share count's change over a year earlier", unit: "ratio" },
  inst_holders: { label: "the number of 13F institutional holders", unit: "count" },
  fii_dii_pct: { label: "the FII + DII holding", unit: "percent" },
  promoter_pct: { label: "the promoter holding", unit: "percent" },
  promoter_pledged_pct: { label: "the pledged share of the promoter holding", unit: "percent" },
  evidence: { label: "the Evidence score", unit: "score" },
};

/** A short name per kill metric (METRIC_LABEL's keys, which tests/test_web_parity.py pins to the pipeline). */
export const KILL_SHORT: Record<string, string> = {
  revenue_ttm: "TTM revenue",
  revenue_ttm_yoy: "TTM revenue growth",
  revenue_q_yoy: "Quarterly revenue growth (YoY)",
  op_margin_ttm: "Operating margin (TTM)",
  roic: "Return on capital",
  fcf_ttm: "Free cash flow (TTM)",
  net_debt: "Net debt",
  rpo: "Contracted revenue (RPO)",
  rpo_yoy: "RPO growth (YoY)",
  shares_yoy: "Share count change (YoY)",
  inst_holders: "Fund holders (13F)",
  fii_dii_pct: "FII + DII holding",
  promoter_pct: "Promoter holding",
  promoter_pledged_pct: "Pledged promoter shares",
  evidence: "Evidence score",
};

/** A kill-criteria (or a card's) metric's short name ("m:revenue_ttm_yoy" -> "TTM revenue growth"). */
export function killName(metric: string): string {
  const key = metric.replace(/^m:/, "");
  const known = KILL_SHORT[key];
  if (known) return known;
  const sig = /^signal:(S\d{1,2})$/.exec(key);
  return sig?.[1] ? `${signalShort(sig[1])} signal strength` : humanize(key);
}

const OP_WORDS: Record<string, string> = {
  "<": "falls below",
  "<=": "falls to or below",
  ">": "rises above",
  ">=": "rises to or above",
  "==": "equals",
};

/** A kill-criteria metric id ("m:roic", "m:signal:S1") as its sentence name and unit. */
export function killMetric(id: string): { label: string; unit: MetricUnit | null } {
  const name = id.replace(/^m:/, "");
  const known = METRIC_LABEL[name];
  if (known) return known;
  const sig = /^signal:(S\d{1,2})$/.exec(name);
  if (sig?.[1]) return { label: `${sig[1]}'s strength (${SIGNAL_NAME[sig[1]] ?? "signal"})`, unit: "strength" };
  return { label: humanize(name), unit: null };
}

/** A kill-criteria value in its metric's unit: 1.20B, 12.5%, 1,340, 4.0% (a holding), 40, 0.35. */
export function metricValue(v: number | string | null | undefined, unit: MetricUnit | null): string {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  if (!Number.isFinite(n)) return "n/a";
  switch (unit) {
    case "money":
      return big(n);
    case "ratio":
      return `${(n * 100).toFixed(1)}%`;
    case "count":
      return Math.round(n).toLocaleString("en-US");
    case "percent":
      return `${n.toFixed(1)}%`;
    case "score":
      return n.toFixed(0);
    case "strength":
      return n.toFixed(2);
    default:
      return measure(n);
  }
}

/** A kill criterion in words, one sentence: "Kill if the TTM operating margin falls below 12.0% (checked from
 * 2026-11-14)." "changes" compares with the value when the thesis was accepted (its baseline). */
export function killSentence(k: { metric: string; operator: string; threshold: number | string | null; baseline?: number | string | null; check_after?: string | null }): string {
  const { label: name, unit } = killMetric(k.metric);
  const cond =
    k.operator === "changes"
      ? `changes${k.baseline === null || k.baseline === undefined ? " from its value when the thesis was accepted" : ` from ${metricValue(k.baseline, unit)}`}`
      : `${OP_WORDS[k.operator] ?? k.operator} ${metricValue(k.threshold, unit)}`;
  return `Kill if ${name} ${cond}${k.check_after ? ` (checked from ${k.check_after})` : ""}.`;
}

const SOURCE_LABEL: Record<string, string> = {
  sec: "SEC",
  sec_13f: "SEC 13F",
  twelvedata: "Twelve Data",
  nse: "NSE",
  bse: "BSE",
};

const PROVIDER_LABEL: Record<string, string> = { gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter" };

export function providerLabel(id: string): string {
  return PROVIDER_LABEL[id] ?? humanize(id);
}

export function sourceLabel(id: string | null | undefined): string {
  if (id === null || id === undefined) return "";
  return SOURCE_LABEL[id] ?? humanize(id);
}

export function label(map: Record<string, string>, id: string | null | undefined): string {
  if (id === null || id === undefined) return "";
  return map[id] ?? humanize(id);
}

/** A money or unit code as people write it ("usd" -> "USD", "percent" -> "%"). */
const CURRENCIES = new Set(["usd", "inr", "eur", "gbp", "jpy", "cny"]);

export function unitLabel(unit: string): string {
  if (unit === "percent") return "%";
  if (CURRENCIES.has(unit)) return unit.toUpperCase();
  return unit.replace(/_/g, " ");
}

/** A verified fact's value with its unit: "$13.2B", "₹371 cr" (an Indian company's money is rupees: the unit is
 * `usd` for any currency, docs/SPEC_ISSUES.md 58), "$2B a year", "18.0%", "2–3 years". */
export function factValue(f: Pick<FactRow, "value_num" | "value_low" | "value_high" | "unit" | "currency">): string {
  const pct = f.unit === "percent";
  const cash = isMoney(f.unit);
  const v = (x: number | null) =>
    x === null ? "n/a" : pct ? `${num(x)}%` : cash ? money(Number(x), f.currency ?? "USD") : big(x);
  const base =
    f.value_num !== null ? v(f.value_num) : f.value_low !== null || f.value_high !== null ? `${v(f.value_low)}–${v(f.value_high)}` : "";
  if (pct || base === "") return base;
  if (cash) return f.unit === "usd_per_year" ? `${base} a year` : base;
  return `${base} ${unitLabel(f.unit)}`;
}

/** A corporate event's detail object as short text: {"index": "S&P MidCap 400"} -> "Index: S&P MidCap 400". */
export function detailText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v !== "object") return String(v);
  if (Array.isArray(v)) return v.map(detailText).filter(Boolean).join(", ");
  return Object.entries(v as Record<string, unknown>)
    .filter(([, x]) => x !== null && x !== undefined && x !== "")
    .map(([k, x]) => `${humanize(k)}: ${typeof x === "object" ? detailText(x) : String(x)}`)
    .join(" · ");
}

export interface DcfRow {
  key: string;
  label: string;
  value: string;
}

// pipeline/signals/reverse_dcf.py writes these inputs (BRIEF §4.7 C2); fractions show as percentages.
const DCF: [key: string, label: string, kind: "pct" | "x" | "big" | "num"][] = [
  ["g_e", "Evidence growth (g_e)", "pct"],
  ["g_star", "Implied growth (g*)", "pct"],
  ["margin", "Operating margin used", "pct"],
  ["s2c", "Sales to capital", "x"],
  ["tax", "Tax rate", "pct"],
  ["discount", "Discount rate", "pct"],
  ["discount_rate", "Discount rate", "pct"],
  ["terminal_growth", "Terminal growth", "pct"],
  ["revenue", "TTM revenue", "big"],
  ["ev", "Enterprise value", "big"],
  ["score", "C2 score", "num"],
];

function fmt(v: unknown, kind: "pct" | "x" | "big" | "num"): string {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  if (!Number.isFinite(n)) return v === null || v === undefined ? "n/a" : String(v);
  switch (kind) {
    case "pct":
      return `${(n * 100).toFixed(1)}%`;
    case "x":
      return `${n.toFixed(2)}x`;
    case "num":
      return n.toFixed(0);
    case "big": {
      const a = Math.abs(n);
      const [d, s] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
      return `${(n / d).toFixed(2)}${s}`;
    }
  }
}

/** The reverse DCF's inputs in a fixed order with readable names; keys it doesn't know come last, as stored. */
export function dcfRows(inputs: Record<string, unknown>): DcfRow[] {
  const known = DCF.filter(([k]) => k in inputs).map(([key, name, kind]) => ({ key, label: name, value: fmt(inputs[key], kind) }));
  const rest = Object.keys(inputs)
    .filter((k) => !DCF.some(([d]) => d === k))
    .sort()
    .map((key) => ({ key, label: humanize(key), value: typeof inputs[key] === "object" ? JSON.stringify(inputs[key]) : String(inputs[key]) }));
  return [...known, ...rest];
}
