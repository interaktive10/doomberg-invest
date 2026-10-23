import { pickSection, stripSection, stripTitle } from "@/lib/cards";
import type { SourceHealth, Thesis } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { code } from "@/lib/format";
import { RED_FLAG_NAME, SIGNAL_PLAIN, signalShort, sourceLabel } from "@/lib/labels";
import { lateSources, sourceStatus, watched } from "@/lib/staleness";

// Home (overhaul PR 5; BRIEF §6): the funnel and What changed come from the digest's body_md, the same text as the
// GitHub issue. pipeline/digest/weekly.py writes "## This week" (one funnel paragraph per market), "## To do",
// "## What changed" (at most 20 "- [TICKER](APP_URL/company/<id>) <text>" lines, or "Nothing changed this week.") and
// "## Health" (the late sources, then the Actions minutes line). Home shows the first and the third: To do is read
// live from the database instead, and health is Home's own Data health. Overhaul PR 6 draws them: the funnel line
// becomes four numbers with bars and one plain sentence, each What changed line a row with a direction, plain words
// and its Evidence move (pipeline/digest/changes.py writes the line shapes read here; the line itself stays in the
// row's tooltip, codes and all). Pure, so tests/home.test.ts covers it.

/** A digest link to a company page ("[MTDR](https://app.example/company/<id>)", APP_URL in the issue) as a path on
 * this site, so it opens here whatever host wrote it. Other links are left as they are. */
export function localLinks(md: string): string {
  return md.replace(/\]\((?:https?:\/\/[^\s/)]+)?(\/company\/[0-9a-f-]{36})\)/gi, "]($1)");
}

/** `legacy`: a digest written before this format (no This week, no What changed: the latest row until the first
 * weekly run after overhaul PR 5) is shown as it is, less its source and quota tables (integration review web-WEB-2). */
export function homeSections(md: string): { funnel: string; changed: string; legacy: string } {
  const funnel = pickSection(md, "This week"); // in a week without scores, the sentence saying why
  const changed = localLinks(pickSection(md, "What changed"));
  const old = md.trim() !== "" && !funnel && !changed;
  const legacy = old ? localLinks(stripTitle(stripSection(stripSection(md, "Source health"), "LLM quota use")).trim()) : "";
  return { funnel, changed, legacy };
}

// ---------------------------------------------------------------- words

const WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

/** 3 -> "Three" (up to ten), else the figure with thousands separators. */
export function countWord(n: number): string {
  return Number.isInteger(n) && n >= 0 && n < WORDS.length ? WORDS[n]! : n.toLocaleString("en-US");
}

function plural(n: number, one: string, many = `${one}s`): string {
  return n === 1 ? one : many;
}

const fmt = (n: number) => n.toLocaleString("en-US");

/** A What changed figure as the rings and To do show it: each score rounded to a whole number with the same Math.round
 * ("72.5" -> "73", "81.5 → 45.2" -> "82 → 45"; PR 6 final review HC-1). A move whose two sides round alike keeps its
 * decimals ("72.6 → 72.9"), so it still reads as a move. The digest's own figure stays in the row's tooltip. */
export function shownDelta(v: string): string {
  const round = (s: string) => s.replace(/\d+(?:\.\d+)?/g, (n) => String(Math.round(Number(n))));
  const sides = v.split(" → ");
  if (sides.length === 2 && sides[0] !== sides[1] && round(sides[0]!) === round(sides[1]!)) return v;
  return round(v);
}

/** A signal's or a red flag's everyday words, lower-case first ("insiders buying shares"); an unknown code as it is. */
function plain(id: string): string {
  const s = SIGNAL_PLAIN[id] ?? RED_FLAG_NAME[id];
  return s === undefined ? id : s[0]!.toLowerCase() + s.slice(1);
}

// ---------------------------------------------------------------- the funnel

/** One market's funnel line: 'US 4,659 → stage 456 → candidates 3 → new 0 · 440 of 456 fire one family, capped at 55'
 * (weekly.py funnel_line): scored, the stage (Evidence 40 or more), the Candidate bucket, the week's shortlist, and the
 * stage names with fewer than two families, whose Evidence is capped. */
export interface FunnelLine {
  market: string;
  scored: number;
  stage: number;
  candidates: number;
  fresh: number;
  oneFamily: number;
  cap: string;
  text: string;
}

const FUNNEL =
  /^([A-Z]{2,3}) ([\d,]+) → stage ([\d,]+) → candidates ([\d,]+) → new ([\d,]+) · ([\d,]+) of [\d,]+ fire one family, capped at (\d+(?:\.\d+)?)$/;

const int = (s: string) => Number(s.replace(/,/g, ""));

/** The funnel lines of This week, one per market paragraph; [] when the section is the sentence of a week without
 * scores (or anything else). */
export function parseFunnel(section: string): FunnelLine[] {
  const out: FunnelLine[] = [];
  for (const para of section.split(/\n\s*\n/)) {
    const text = para.trim();
    const m = FUNNEL.exec(text);
    if (m) {
      out.push({
        market: m[1]!,
        scored: int(m[2]!),
        stage: int(m[3]!),
        candidates: int(m[4]!),
        fresh: int(m[5]!),
        oneFamily: int(m[6]!),
        cap: m[7]!,
        text,
      });
    }
  }
  return out;
}

export interface FunnelTotals {
  markets: string[];
  scored: number;
  stage: number;
  candidates: number;
  fresh: number;
  oneFamily: number;
  cap: string;
}

/** The markets' lines added up (the US alone while India is paused); null without any. */
export function funnelTotals(lines: readonly FunnelLine[]): FunnelTotals | null {
  if (lines.length === 0) return null;
  const sum = (k: "scored" | "stage" | "candidates" | "fresh" | "oneFamily") => lines.reduce((a, l) => a + l[k], 0);
  return {
    markets: lines.map((l) => l.market),
    scored: sum("scored"),
    stage: sum("stage"),
    candidates: sum("candidates"),
    fresh: sum("fresh"),
    oneFamily: sum("oneFamily"),
    cap: lines[0]!.cap,
  };
}

/** A funnel bar's length in percent of the first: on a log scale, so 3 of 4,659 still shows (the mock's widths); 0 is
 * an empty track. */
export function funnelWidth(value: number, max: number): number {
  if (!(value > 0) || !(max > 0)) return 0;
  return Math.max(2, Math.min(100, Math.round((Math.log10(value + 1) / Math.log10(max + 1)) * 100)));
}

export type FunnelKey = "scored" | "stage" | "board" | "new";

export interface FunnelStep {
  key: FunnelKey;
  value: number;
  label: string;
  /** the phone's one word (the phone mock: scored, signal, on board, new) */
  short: string;
  width: number;
}

const MARKET_WORD: Record<string, string> = { US: "US", IN: "Indian" };

/** The four steps the strip draws. */
export function funnelSteps(t: FunnelTotals): FunnelStep[] {
  const one = t.markets.length === 1 ? MARKET_WORD[t.markets[0]!] : undefined;
  const steps: [FunnelKey, number, string, string][] = [
    ["scored", t.scored, one ? `${one} companies scored` : "companies scored", "scored"],
    ["stage", t.stage, "show real evidence", "signal"],
    ["board", t.candidates, "on the board", "on board"],
    ["new", t.fresh, "new this week", "new"],
  ];
  return steps.map(([key, value, label, short]) => ({ key, value, label, short, width: funnelWidth(value, t.scored) }));
}

/** The strip's heading: "From 4,659 companies to 3 ideas". */
export function funnelTitle(t: FunnelTotals): string {
  if (t.candidates === 0) return `${fmt(t.scored)} ${plural(t.scored, "company", "companies")} scored, none on the board`;
  return `From ${fmt(t.scored)} ${plural(t.scored, "company", "companies")} to ${fmt(t.candidates)} ${plural(t.candidates, "idea")}`;
}

/** The one insight under the strip, its figure first (shown bold): "440 of 456" + " show only one kind of signal, ...".
 * Null when nothing reached the stage. */
export function funnelInsight(t: FunnelTotals): { lead: string; rest: string } | null {
  if (t.stage === 0) return null;
  if (t.oneFamily === 0) return { lead: "Every name", rest: " with real evidence shows at least two kinds of signal." };
  const one = t.oneFamily === 1;
  return {
    lead: `${fmt(t.oneFamily)} of ${fmt(t.stage)}`,
    rest:
      ` ${one ? "shows" : "show"} only one kind of signal, so ${one ? "its" : "their"} score stops at ${t.cap}. ` +
      "A second kind is what lifts a name onto the board.",
  };
}

/** Home's one line under "This week": the answer first. */
export function headline(s: { digest: boolean; totals: FunnelTotals | null; funnel: string; legacy: string }): string {
  if (!s.digest) return "No digest yet: the weekly run writes the first one on Saturday.";
  const t = s.totals;
  if (t) {
    if (t.fresh > 0) {
      const lead = `${countWord(t.fresh)} new ${plural(t.fresh, "idea")} cleared the bar this week.`;
      return t.candidates > t.fresh ? `${lead} ${countWord(t.candidates)} on the board in all.` : lead;
    }
    if (t.candidates > 0) {
      return `A quiet week: nothing new cleared the bar. ${countWord(t.candidates)} ${plural(t.candidates, "idea is", "ideas are")} still worth your time.`;
    }
    return "A quiet week: nothing cleared the bar.";
  }
  if (s.funnel) return "No scores this week, so the board stands as it was.";
  if (s.legacy) return "This digest predates the funnel; Saturday's run writes the next one.";
  return "The digest says nothing about this week yet.";
}

// ---------------------------------------------------------------- What changed

/** Which way a change points: up (good: joined the board, Evidence rose), down (left the board, Evidence fell), flat,
 * bad (excluded, a hard red flag) or news (a verified fact). */
export type ChangeDir = "up" | "down" | "flat" | "bad" | "news";

export interface ChangeItem {
  code: string;
  href: string;
  /** the digest's text after the link, codes and all (the row's tooltip) */
  raw: string;
  dir: ChangeDir;
  /** what happened, in plain words: "left the board", "Evidence rose" */
  title: string;
  /** why, in plain words: "Stopped: cash flow rising ahead of profits" */
  why: string;
  /** the figure on the right: Evidence "81 → 45" or "72.5", or a Gap level */
  delta: { label: "Evidence" | "Gap"; value: string } | null;
  /** a new candidate's families (scores.families), for its evidence dots */
  families: string[];
  /** a bucket move's pipeline labels ("Candidate", "Early", "Priced-in") */
  from: string | null;
  to: string | null;
}

const BUCKET_WORD: Record<string, string> = { Candidate: "the board", Early: "Early", "Priced-in": "Priced in", Excluded: "Excluded" };
const B = "(Candidate|Early|Priced-in)";
const NUM = "(\\d+(?:\\.\\d+)?)";

interface Reasons {
  started: string[];
  stopped: string[];
  hard: string[];
  soft: string[];
  cleared: string[];
  move: [string, string] | null;
  level: { label: "Evidence" | "Gap"; value: string } | null;
  other: string[];
}

const VERB: Record<string, "started" | "stopped" | "hard" | "soft" | "cleared"> = {
  fired: "started",
  stopped: "stopped",
  "hard flag": "hard",
  "soft flag": "soft",
  cleared: "cleared",
};

/** A change's detail ("S1, S3 fired, S4 stopped, R2 soft flag, Evidence 62 → 48", "Gap 58.3", "not scored this
 * week") taken apart (changes.py reasons and _gap). */
function reasons(detail: string): Reasons {
  const r: Reasons = { started: [], stopped: [], hard: [], soft: [], cleared: [], move: null, level: null, other: [] };
  const ids = /((?:[SR]\d{1,2}, )*[SR]\d{1,2}) (fired|stopped|hard flag|soft flag|cleared)/g;
  for (const m of detail.matchAll(ids)) r[VERB[m[2]!]!].push(...m[1]!.split(", "));
  const move = new RegExp(`Evidence ${NUM} → ${NUM}`).exec(detail);
  if (move) r.move = [move[1]!, move[2]!];
  const ev = new RegExp(`Evidence ${NUM}(?![\\d.]| →)`).exec(detail);
  const gap = new RegExp(`Gap ${NUM}`).exec(detail);
  if (!move && ev) r.level = { label: "Evidence", value: ev[1]! };
  else if (gap) r.level = { label: "Gap", value: gap[1]! };
  if (/not scored this week/.test(detail)) r.other.push("Not scored this week");
  if (/Gap not known this week/.test(detail)) r.other.push("Gap not known this week");
  if (/no signal fired/.test(detail)) r.other.push("No signal fired");
  return r;
}

function whyOf(r: Reasons): string {
  const list = (xs: string[]) => xs.map(plain).join(", ");
  const parts = [
    r.started.length ? `New: ${list(r.started)}` : "",
    r.stopped.length ? `Stopped: ${list(r.stopped)}` : "",
    r.hard.length ? `Red flag: ${list(r.hard)}` : "",
    r.soft.length ? `Watch out: ${list(r.soft)}` : "",
    r.cleared.length ? `Cleared: ${list(r.cleared)}` : "",
    ...r.other,
  ];
  return parts.filter(Boolean).join(" · ");
}

function deltaOf(r: Reasons): ChangeItem["delta"] {
  return r.move ? { label: "Evidence", value: `${r.move[0]} → ${r.move[1]}` } : r.level;
}

/** Up or down by an Evidence move, else flat. */
function byMove(r: Reasons): ChangeDir {
  if (!r.move) return "flat";
  const d = Number(r.move[1]) - Number(r.move[0]);
  return d > 0 ? "up" : d < 0 ? "down" : "flat";
}

type Described = Pick<ChangeItem, "dir" | "title" | "why" | "delta" | "families" | "from" | "to">;

/** One What changed line's text (after the link) in plain words. A text this doesn't know is its own title. */
export function describeChange(text: string): Described {
  const t = text.trim();
  const base = { families: [] as string[], from: null as string | null, to: null as string | null };
  let m: RegExpExecArray | null;

  if ((m = /^new candidate \(#(\d+)\)(?:: (.*))?$/.exec(t))) {
    const detail = m[2] ?? "";
    const fired = /^((?:S\d{1,2}, )*S\d{1,2}) fired(?: \(([^)]*)\))?/.exec(detail);
    const r = reasons(detail);
    return {
      ...base,
      dir: "up",
      title: `is new on the board (#${m[1]})`,
      why: fired ? fired[1]!.split(", ").map(plain).join(", ").replace(/^./, (c) => c.toUpperCase()) : r.other.join(" · "),
      delta: r.level?.label === "Evidence" ? r.level : null,
      families: fired?.[2] ? fired[2].split(", ").filter(Boolean) : [],
      to: "Candidate",
    };
  }
  if ((m = /^now priced in \(([^)]*)\)$/.exec(t))) {
    return { ...base, dir: "flat", title: "is now priced in", why: "", delta: reasons(m[1]!).level, to: "Priced-in" };
  }
  if ((m = /^entered Priced-in \(([^)]*)\)(?:: (.*))?$/.exec(t))) {
    const r = reasons(m[2] ?? "");
    return { ...base, dir: "flat", title: "is now priced in", why: whyOf(r), delta: r.move ? deltaOf(r) : reasons(m[1]!).level, to: "Priced-in" };
  }
  if ((m = new RegExp(`^moved from ${B} to ${B}: (.*)$`).exec(t))) {
    const [from, to] = [m[1]!, m[2]!];
    const r = reasons(m[3]!);
    const dir: ChangeDir = to === "Candidate" ? "up" : from === "Candidate" ? "down" : byMove(r);
    return { ...base, dir, title: `moved from ${BUCKET_WORD[from]} to ${BUCKET_WORD[to]}`, why: whyOf(r), delta: deltaOf(r), from, to };
  }
  if ((m = new RegExp(`^left ${B}: (.*)$`).exec(t))) {
    const from = m[1]!;
    const r = reasons(m[2]!);
    return { ...base, dir: from === "Priced-in" ? "flat" : "down", title: `left ${BUCKET_WORD[from]}`, why: whyOf(r), delta: deltaOf(r), from };
  }
  if ((m = new RegExp(`^entered ${B}: (.*)$`).exec(t))) {
    const to = m[1]!;
    const r = reasons(m[2]!);
    const title = to === "Candidate" ? "joined the board" : to === "Early" ? "entered Early" : "is now priced in";
    return { ...base, dir: to === "Priced-in" ? "flat" : "up", title, why: whyOf(r), delta: deltaOf(r), to };
  }
  if ((m = /^now Excluded: (.*)$/.exec(t))) {
    const r = reasons(m[1]!);
    return { ...base, dir: "bad", title: "was excluded", why: whyOf(r), delta: deltaOf(r), to: "Excluded" };
  }
  if ((m = /^no longer Excluded: (.*)$/.exec(t))) {
    const r = reasons(m[1]!);
    return { ...base, dir: "up", title: "is no longer excluded", why: whyOf(r), delta: deltaOf(r), from: "Excluded" };
  }
  if ((m = new RegExp(`^Evidence ${NUM} → ${NUM}(?:: (.*))?$`).exec(t))) {
    const r = reasons(t);
    const dir = byMove(r);
    return { ...base, dir, title: dir === "up" ? "Evidence rose" : dir === "down" ? "Evidence fell" : "Evidence moved", why: whyOf(r), delta: deltaOf(r) };
  }
  if ((m = /^new verified (.+?): (.*)$/.exec(t))) {
    return { ...base, dir: "news", title: `new verified ${m[1]}`, why: m[2]!, delta: null };
  }
  if ((m = /^(.+?) (raised|lowered|widened|narrowed|changed): (.*)$/.exec(t)) && !/\b[SR]\d{1,2}\b/.test(m[1]!)) {
    const dir: ChangeDir = m[2] === "raised" ? "up" : m[2] === "lowered" ? "down" : "news";
    return { ...base, dir, title: `${m[1]} ${m[2]}`, why: m[3]!, delta: null };
  }
  const r = reasons(t);
  const signals = r.started.length + r.stopped.length + r.hard.length + r.soft.length + r.cleared.length;
  if (signals > 0) {
    const [dir, title]: [ChangeDir, string] = r.hard.length
      ? ["bad", "got a red flag"]
      : r.soft.length
        ? ["down", "got a warning flag"]
        : r.stopped.length && !r.started.length
          ? ["down", r.stopped.length === 1 ? "lost a signal" : "lost signals"]
          : r.started.length && !r.stopped.length
            ? ["up", r.started.length === 1 ? "gained a signal" : "gained signals"]
            : r.cleared.length && !r.started.length && !r.stopped.length
              ? ["up", "cleared a flag"]
              : [byMove(r), "signals changed"];
    return { ...base, dir, title, why: whyOf(r), delta: deltaOf(r) };
  }
  return { ...base, dir: "flat", title: t, why: "", delta: null };
}

const LINE = /^\s*[-*]\s+\[([^\]]+)\]\(([^)\s]+)\)\s+(.+?)\s*$/;

/** What changed's linked lines, each in plain words; a section with none ("Nothing changed this week.") gives []. */
export function changeItems(section: string): ChangeItem[] {
  const out: ChangeItem[] = [];
  for (const line of section.split("\n")) {
    const m = LINE.exec(line);
    if (m) out.push({ code: m[1]!, href: m[2]!, raw: m[3]!, ...describeChange(m[3]!) });
  }
  return out;
}

const BUCKET_LABEL = { candidate: "Candidate", early: "Early", priced_in: "Priced-in" } as const;

/** The lines that say a company left `bucket` (Candidates' "Left the board this week"): "left Candidate: ..." and
 * "moved from Candidate to ...". */
export function leftBucket(items: readonly ChangeItem[], bucket: keyof typeof BUCKET_LABEL): ChangeItem[] {
  const label = BUCKET_LABEL[bucket];
  return items.filter((c) => c.from === label && c.to !== label);
}

// ---------------------------------------------------------------- To do and Coming up

/** A To do row's line and its button: a card to accept or pass, or a review to give a verdict on. `short` is the
 * phone's one line (the phone mock's "Card ready · Evidence 94"; PR 6 final review HC-10). */
export function todoAsk(
  state: string,
  f?: { now: number | null; kills: readonly string[] },
): { ask: string; short: string; action: string; alert: boolean } {
  if (state === "review") {
    const hit = (f?.kills ?? []).filter((k) => k === "triggered").length;
    return hit > 0
      ? {
          ask: `${hit === 1 ? "A kill check" : `${hit} kill checks`} triggered: record a verdict`,
          short: `${hit === 1 ? "Kill check" : `${hit} kill checks`} triggered`,
          action: "Open review",
          alert: true,
        }
      : { ask: "New filing in: is the thesis still intact?", short: "New filing in", action: "Open review", alert: false };
  }
  const ev = f?.now === null || f?.now === undefined ? "" : ` · Evidence ${Math.round(f.now)}`;
  return { ask: `New research card: accept it or pass${ev}`, short: `Card ready${ev}`, action: "Review card", alert: false };
}

/** About how long To do takes: three minutes a row, rounded up to five. */
export function todoMinutes(n: number): number {
  return n <= 0 ? 0 : Math.ceil((n * 3) / 5) * 5;
}

export interface Upcoming {
  id: string;
  code: string;
  what: string;
  date: string;
}

type Live = Pick<Thesis, "id" | "state" | "evidence_pack" | "card_json" | "next_review" | "companies">;

/** Coming up: each live card or thesis's next filing from today on, soonest first. A thesis's next review date
 * (accept() writes the pack's next filing window into it, a review verdict moves it on) wins over its pack's window;
 * a research card has only the pack's. With the number of kill checks it carries (`kills`, else the card's own). */
export function comingUp(list: readonly Live[], today: string, kills: ReadonlyMap<string, number> = new Map(), max = 6): Upcoming[] {
  const out: Upcoming[] = [];
  for (const t of list) {
    if (!["research", "thesis", "position", "review"].includes(t.state) || !t.companies) continue;
    const nf = t.evidence_pack?.next_filing as { form?: unknown; closes?: unknown } | undefined;
    const closes = typeof nf?.closes === "string" && /^\d{4}-\d{2}-\d{2}$/.test(nf.closes) ? nf.closes : null;
    const date = t.state !== "research" && t.next_review ? t.next_review : closes;
    if (date === null || date < today) continue;
    const form = closes === date && typeof nf?.form === "string" && nf.form ? nf.form : null;
    const own = (t.card_json as { kill_criteria?: unknown }).kill_criteria;
    const k = kills.get(t.id) ?? (Array.isArray(own) ? own.length : 0);
    // a filing window closes by its date; a thesis's own date is its next scheduled review, not a deadline for one
    // already open (PR 6 final review DT-5)
    const when = form ? `${form} by ${shortDate(date)}` : `next review ${shortDate(date)}`;
    const what = `${when}${k > 0 ? ` · ${k} kill ${plural(k, "check")}` : ""}`;
    out.push({ id: t.id, code: code(t.companies), what, date });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date) || a.code.localeCompare(b.code)).slice(0, max);
}

// ---------------------------------------------------------------- On the board and Data health

/** An On the board row's one line: its first two fired signals by their short names, as the Company page names them
 * ("Insider buying · Earnings quality"); the row's title says every fired signal in everyday words (boardWhyAll). */
export function boardWhy(signals: readonly string[]): string {
  const words = signals.slice(0, 2).map(signalShort);
  return words.length === 0 ? "No signal fired" : words.join(" · ");
}

/** Every fired signal in everyday words, for the row's tooltip: "Insiders buying shares · cash flow rising ahead of
 * profits · verified wins in its filings". */
export function boardWhyAll(signals: readonly string[]): string {
  return signals.length === 0 ? "No signal fired" : signals.map(plain).join(" · ").replace(/^./, (c) => c.toUpperCase());
}

export type HealthState = "ok" | "late" | "down" | "resting";

export interface HealthRow {
  source: string;
  name: string;
  state: HealthState;
  when: string;
}

const HEALTH_NAME: Record<string, string> = { sec: "SEC filings", twelvedata: "Weekly prices", sec_13f: "Fund holdings (13F)" };

/** A source's name after the first in a sentence: "Weekly prices" -> "weekly prices"; one that starts with an acronym
 * ("SEC filings", "NSE") stays as it is. Home's late line and Settings' line both say names this way. */
export function midSentence(name: string): string {
  return /^[A-Z][a-z]/.test(name) ? name[0]!.toLowerCase() + name.slice(1) : name;
}

/** Whether a source's Data health name is a plural noun ("SEC filings are", "Weekly prices need"), so a sentence
 * about it alone takes the plural verb. */
export function pluralSource(source: string): boolean {
  return source in HEALTH_NAME;
}
/** The provider a Data health name doesn't already say: "Weekly prices" come from Twelve Data. */
const HEALTH_PROVIDER: Record<string, string> = { twelvedata: "Twelve Data" };

/** Data health: each source the pipeline reads (lib/staleness.ts watched), with a state for its dot and its last
 * success ("Sep 18"), or why not ("late · Sep 2", "stale", "never"). */
export function healthRows(sources: readonly SourceHealth[], now: Date): HealthRow[] {
  return watched(sources).map((s) => {
    const status = sourceStatus(s, sources, now);
    const state: HealthState = status === "ok" ? "ok" : status.startsWith("late") ? "late" : status.startsWith("fallback") ? "resting" : "down";
    const day = s.last_success ? shortDate(s.last_success) : "never";
    const down = s.last_success === null && !s.stale ? "never" : "stale";
    const when = { ok: day, late: `late · ${day}`, resting: "not needed", down }[state];
    return { source: s.source, name: HEALTH_NAME[s.source] ?? sourceLabel(s.source), state, when };
  });
}

/** The stale-data line (BRIEF §2.7), or null when every source is on time. It names the late sources as the Data health
 * rows above it do, with the provider where the row's name doesn't say it: "Weekly prices (Twelve Data) are out of
 * date, so scores that read them may be behind." */
export function lateLine(sources: readonly SourceHealth[], now: Date): string | null {
  const late = lateSources(sources, now);
  if (late.length === 0) return null;
  const names = late.map((s, i) => {
    const name = HEALTH_NAME[s.source] ?? sourceLabel(s.source);
    const said = i > 0 ? midSentence(name) : name; // "and weekly prices"
    return HEALTH_PROVIDER[s.source] ? `${said} (${HEALTH_PROVIDER[s.source]})` : said;
  });
  const list = names.length === 1 ? names[0]! : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  const one = names.length === 1 && !pluralSource(late[0]!.source); // "SEC filings are", "NSE is"
  return `${list} ${one ? "is" : "are"} out of date, so scores that read ${one ? "it" : "them"} may be behind.`;
}
