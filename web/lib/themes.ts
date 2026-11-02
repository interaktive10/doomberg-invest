// Themes v2 (pipeline/reports/themes.py writes reports('themes', week); docs/SPEC_ISSUES.md 68): a library of demand
// chains (a driver, read one way, reaching the companies its keywords match) with this week's numbers, rethought
// monthly. The body's shape and the plain words the Themes screen shows. Pure, so tests/themes.test.ts covers it.

export type Status = "building" | "priced_in" | "watching" | "fading";

export interface ThemeName {
  company_id: string;
  code: string | null;
  name: string;
  market: "us" | "in";
  industry: string;
  evidence: number | null;
  bucket: string | null;
  move: number | null;
  demand: boolean;
  /** market cap as of the latest scored week (reports before 2026-11-02 lack it) */
  cap?: number | null;
}

export interface ThemeNote {
  week: string;
  decision: "keep" | "edit" | "retire" | "new";
  text: string;
}

export interface HistoryCheck {
  years: number;
  first: number;
  last: number;
  tail_years: number;
  tail_beat: number;
  tail_excess: number | null;
  other_excess: number | null;
}

/** The months a reading compares and their averages (pipeline/reports/drivers.py basis), or a filings theme's share. */
export type Basis =
  | {
      transform: "yoy" | "level" | "cohort";
      now: { from: string; to: string; value: number };
      then: { from: string; to: string; value: number };
      change: number | null;
      peak: { year: number; value: number } | null;
      through: string;
    }
  | { transform: "filings"; share: number; typical: number | null };

export interface LibraryTheme {
  /** the numbers behind the reading (reports before 2026-11-02 lack it) */
  basis?: Basis | null;
  slug: string;
  title: string;
  category: string;
  driver: string;
  transform: "yoy" | "level" | "cohort";
  lag_months: number;
  keywords: string[];
  why: string;
  wrong_if: string;
  origin: "starter" | "ai";
  born: string | null;
  notes: ThemeNote[];
  z: number | null;
  signal: string;
  chart: [string, number][];
  companies: number;
  priced: number;
  with_demand: number;
  share: number;
  move: number | null;
  market_move: number | null;
  run: number | null;
  markets: ("us" | "in")[];
  status: Status;
  history: HistoryCheck | null;
  names: ThemeName[];
  undervalued: number;
}

export interface RetiredTheme {
  slug: string;
  title: string;
  category: string;
  week: string;
  note: string;
  notes: ThemeNote[];
}

export interface ThemesReport {
  version: 2;
  week: string;
  /** the day the numbers were computed */
  as_of?: string;
  library: LibraryTheme[];
  retired: RetiredTheme[];
  drivers: Record<string, string>;
  /** each driver's unit (reports before 2026-11-02 lack them) */
  units?: Record<string, string>;
  note: string;
  last_rethink: string | null;
  next_rethink: string;
  rethought: boolean;
}

/** A v1 report (before the library) reads as none: the screen waits for Saturday's first library. */
export function isLibrary(body: unknown): body is ThemesReport {
  return !!body && typeof body === "object" && (body as { version?: unknown }).version === 2 && Array.isArray((body as { library?: unknown }).library);
}

// Plain words for the four statuses (Manzoor, 2026-11-02: "i didn't understand building, fading, etc"): what the
// trigger is doing and whether the price has already moved. The rule is pipeline/reports/themes.py status_of: the
// trigger at least half a z-score above (or below) its normal, and the companies not more than 10 points ahead of the market over 12 months.
export const STATUS: Record<Status, { label: string; tone: "up" | "warn" | "muted" | "down"; hint: string }> = {
  building: { label: "Early: demand up, price not yet", tone: "up", hint: "the trigger is running above normal and these stocks haven't run ahead of the market yet. This is the list to read" },
  priced_in: { label: "Late: price already up", tone: "warn", hint: "the trigger is running above normal, but these stocks already beat the market by more than 10 points over the past 12 months" },
  watching: { label: "Nothing unusual yet", tone: "muted", hint: "the trigger is close to its normal level. Kept in case it moves" },
  fading: { label: "Trigger cooling", tone: "down", hint: "the trigger is running below normal: a headwind for these companies" },
};

/** A short chip for each status where the long label doesn't fit. */
export const STATUS_SHORT: Record<Status, string> = { building: "Early", priced_in: "Late", watching: "Quiet", fading: "Cooling" };

/** A z-score in words, against the series' own past 20 years: 1.3 -> "higher than 90% of the past 20 years". */
export function zWords(z: number | null): string {
  if (z === null || !Number.isFinite(z)) return "";
  const p = Math.round(normalCdf(z) * 100);
  if (p >= 50) return `higher than ${Math.min(p, 99)}% of the past 20 years`;
  return `lower than ${Math.min(100 - p, 99)}% of the past 20 years`;
}

/** The standard normal CDF (Abramowitz and Stegun 26.2.17, error < 1e-7). */
function normalCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989422804014327 * Math.exp((-z * z) / 2);
  const tail = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return z >= 0 ? 1 - tail : tail;
}

export const STATUS_ORDER: Status[] = ["building", "priced_in", "watching", "fading"];

/** "4 years", "18 months", "6 months". */
export function span(months: number): string {
  if (months % 12 === 0 && months >= 24) return `${months / 12} years`;
  if (months === 12) return "1 year";
  return `${months} months`;
}

/** How the driver is read, in words: "vs a year ago", "vs its 10-year average", "the wave of 4 years ago". */
export function readingWords(t: Pick<LibraryTheme, "transform" | "lag_months" | "driver">): string {
  if (t.driver === "filings") return "how many of its companies report rising demand";
  if (t.transform === "cohort") return `the 12 months that ended ${span(t.lag_months)} ago, against the decade before`;
  if (t.transform === "level") return "against its 10-year average";
  return "against a year ago";
}

/** When the driver reaches the companies: "now", "about 6 months later" (a cohort's wait is in its reading). */
export function lagWords(t: Pick<LibraryTheme, "transform" | "lag_months">): string {
  if (t.transform === "cohort" || t.lag_months === 0) return "now";
  return `about ${span(t.lag_months)} later`;
}

/** The history check in one sentence, or null without enough years. */
export function historyLine(h: HistoryCheck | null): string | null {
  if (!h) return null;
  if (h.tail_years === 0) return `In ${h.years} years (${h.first}–${h.last}) the driver never gave a clear signal.`;
  const ex = h.tail_excess === null ? "" : `, by ${pct(h.tail_excess)} on average`;
  return `In the ${h.tail_years} of ${h.years} years (${h.first}–${h.last}) the driver said yes, these companies beat the market ${h.tail_beat} times${ex}.`;
}

/** 0.123 -> "+12%", -0.04 -> "-4%". */
export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const p = Math.round(v * 100);
  return p > 0 ? `+${p}%` : p < 0 ? `-${Math.abs(p)}%` : "0%";
}

/** The library grouped by category for the picker, categories in first-seen order. */
export function byCategory(lib: readonly LibraryTheme[]): [string, LibraryTheme[]][] {
  const out = new Map<string, LibraryTheme[]>();
  for (const t of lib) out.set(t.category, [...(out.get(t.category) ?? []), t]);
  return [...out];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2021-10" -> "Oct 2021". */
export function monthText(ym: string): string {
  const [y, m] = ym.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

/** "Oct 2021–Sep 2022", "Jul–Sep 2026". */
export function spanText(from: string, to: string): string {
  if (from === to) return monthText(from);
  return from.slice(0, 4) === to.slice(0, 4) ? `${MONTHS[Number(from.slice(5)) - 1]}–${monthText(to)}` : `${monthText(from)}–${monthText(to)}`;
}

/** A driver's value in its unit's words: "13.9 million a year", "$124.3 billion", "6.85%", "112.4 on its index". */
export function valueText(v: number, unit: string): string {
  const n = (x: number) => x.toLocaleString("en-US", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 1 });
  const perYear = unit.endsWith(" a year") ? " a year" : "";
  if (unit.startsWith("million dollars")) {
    if (v >= 1e6) return `$${n(v / 1e6)} trillion${perYear}`;
    return v >= 1000 ? `$${n(v / 1000)} billion${perYear}` : `$${n(v)} million${perYear}`;
  }
  if (unit === "percent") return `${v.toFixed(2)}%`;
  if (unit === "index") return `${n(v)} on its index`;
  if (unit.startsWith("dollars ")) return `$${n(v)} ${unit.slice("dollars ".length)}`;
  return unit ? `${n(v)} ${unit}` : n(v);
}

/** "16% below", "3% above" (a change as words). */
function changeWords(c: number | null): string {
  if (c === null || !Number.isFinite(c)) return "about the same as";
  const p = Math.round(Math.abs(c) * 100);
  return p === 0 ? "about the same as" : `${p}% ${c > 0 ? "above" : "below"}`;
}

/** The data behind a theme in a line or two (2026-11-02: "you need to support it with data ... which year had the
 * highest sales"): the months its reading compares, their averages, the change, and the highest year of the last 20.
 * Empty for a report without it. */
export function basisLines(t: Pick<LibraryTheme, "basis" | "driver" | "with_demand" | "companies" | "lag_months">, r: Pick<ThemesReport, "drivers" | "units">): string[] {
  const b = t.basis;
  if (!b) return [];
  if (b.transform === "filings") {
    const own = `${t.with_demand} of ${t.companies} companies (${Math.round(b.share * 100)}%) report rising demand in their filings`;
    return [b.typical === null ? `${own}.` : `${own}; in the typical industry it is ${Math.round(b.typical * 100)}%.`];
  }
  const name = r.drivers[t.driver] ?? t.driver;
  const unit = r.units?.[t.driver] ?? "";
  const now = `${valueText(b.now.value, unit)}`;
  const then = valueText(b.then.value, unit);
  const lines =
    b.transform === "cohort"
      ? [`The wave it counts: ${spanText(b.now.from, b.now.to)}, when ${name} averaged ${now}: ${changeWords(b.change)} the 10 years before it (${then}).`]
      : b.transform === "yoy"
        ? [`${spanText(b.now.from, b.now.to)}: ${name} averaged ${now}, ${changeWords(b.change)} the same months a year before (${then}).`]
        : [`${spanText(b.now.from, b.now.to)}: ${name} averaged ${now}, ${changeWords(b.change)} its average of the 10 years before (${then}).`];
  if (b.peak) lines.push(`Highest year of the last 20: ${b.peak.year} (${valueText(b.peak.value, unit)}). Data through ${monthText(b.through)}, from FRED.`);
  return lines;
}

/** The basis in a few words for a theme's card: "Oct 2021–Sep 2022: 16% below the decade before". */
export function basisShort(t: Pick<LibraryTheme, "basis">): string | null {
  const b = t.basis;
  if (!b) return null;
  if (b.transform === "filings") return b.typical === null ? null : `${Math.round(b.share * 100)}% report rising demand vs ${Math.round(b.typical * 100)}% typical`;
  const vs = b.transform === "yoy" ? "a year before" : "the decade before";
  return `${spanText(b.now.from, b.now.to)}: ${changeWords(b.change)} ${vs}`;
}

/** The "Rethink now" button's state (docs/SPEC_ISSUES.md 76): once a day (UTC, the pipeline's day), and not while a
 * request waits. */
export function rethinkState(lastRethink: string | null, requestedAt: string | null, now: Date): { kind: "ready" | "pending" | "done_today"; since?: string } {
  const today = now.toISOString().slice(0, 10);
  if (lastRethink === today) return { kind: "done_today" };
  if (requestedAt) return { kind: "pending", since: requestedAt };
  return { kind: "ready" };
}

