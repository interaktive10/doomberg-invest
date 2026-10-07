// Display names for the ids the pipeline stores (BRIEF §1.4 signals, §1.5 red flags, §1.6 context, §4.7 reverse DCF).
// Display only: forms, URLs and the database keep the ids.

/** snake_case or kebab-case id -> "Sentence case" ("open_market_buy" -> "Open market buy"). */
export function humanize(id: string | null | undefined): string {
  if (id === null || id === undefined) return "";
  const s = id.replace(/[_-]+/g, " ").trim();
  return s === "" ? "" : s[0]!.toUpperCase() + s.slice(1);
}

export const BUCKET_LABEL: Record<string, string> = {
  candidate: "Candidate",
  early: "Early",
  priced_in: "Priced-in",
  excluded: "Excluded",
  none: "No bucket",
};

export const FAMILY_LABEL: Record<string, string> = {
  fundamentals: "Fundamentals",
  behavior: "Behavior",
  text: "Text",
  structural: "Structural",
  capex: "Capex",
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
  S11: "Capex propagation",
  S12: "Cycle position",
};

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
  C4: "Attention: news-mention percentile",
};

export const ACTION_LABEL: Record<string, string> = {
  note: "Note",
  start_position: "Start position",
  add: "Add",
  trim: "Trim",
  exit: "Exit",
  review: "Review",
};

/** The screener's metrics (lib/screener.ts METRICS), with the unit a filter value is in. */
export const METRIC_LABEL: Record<string, string> = {
  revenue_ttm: "Revenue, TTM (currency units)",
  revenue_yoy: "Revenue growth YoY (0.10 = 10%)",
  opm: "Operating margin (0.20 = 20%)",
  roic: "ROIC (0.15 = 15%)",
  fcf_ttm: "Free cash flow, TTM (currency units)",
  ccr: "Cash conversion, CFO / net income (x)",
  nd_to_ebitda: "Net debt / EBITDA (x)",
  share_change_yoy: "Share count change YoY (−0.02 = −2%)",
  market_cap: "Market cap (currency units)",
  ev: "Enterprise value (currency units)",
  return_52w: "52-week return (0.25 = 25%)",
};

const SOURCE_LABEL: Record<string, string> = {
  sec: "SEC",
  sec_13f: "SEC 13F",
  stooq: "Stooq",
  yahoo: "Yahoo Finance",
  gdelt: "GDELT",
  fred: "FRED",
  eia: "EIA",
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
