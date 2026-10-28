import { CITE, stripTitle } from "@/lib/cards";
import { minus, type ChartFormat } from "@/lib/chart";
import { shortDate } from "@/lib/dates";
import { money } from "@/lib/format";
import { FAMILY_LABEL, humanize, killMetric, killName, label, metricValue, SIGNAL_NAME, SIGNAL_PLAIN } from "@/lib/labels";
import { MIN_FAMILIES, SINGLE_FAMILY_CAP, SOFT_FLAG_PENALTY, type Breakdown, type GapPart } from "@/lib/why";

// The short names (lib/labels.ts, so lib/cards.ts can name a citation without importing this file) and money
// (lib/format.ts, so the client charts can format with it) stay importable from here.
export { GAP_SHORT, KILL_SHORT, killName, SIGNAL_SHORT, signalShort } from "@/lib/labels";
export { money } from "@/lib/format";

// Plain words for the Company, Theses and Thesis screens (overhaul PR 6): a short name per signal and Gap part, one
// line each from the stored inputs, the kill criteria as a checklist, the insiders' buying as bars, a year's change
// under a chart and a card cut into its sections. Display only: the codes (S4, C1, m:roic) stay in titles and "Details"
// disclosures. Pure, so tests/explain.test.ts covers it.

function n(v: unknown): number | null {
  const x = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : Number.NaN;
  return Number.isFinite(x) ? x : null;
}

/** 0.106 -> "10.6%", 0.05 -> "5%" (a fraction as a percentage, at most one decimal). */
export function pc(x: number): string {
  return `${Number((x * 100).toFixed(1))}%`;
}

/** 3.94 -> "3.9×". */
function times(x: number): string {
  return `${x.toFixed(1)}×`;
}

// ------------------------------------------------------------------------------------------------ scores and buckets

/** Bucket names as the screens say them (the Candidates tabs: On the board, Early, Watch, Priced in). */
export const BOARD_LABEL: Record<string, string> = {
  candidate: "On the board",
  early: "Early",
  watch: "Watch",
  priced_in: "Priced in",
  excluded: "Excluded",
  none: "Not on the board",
};

/** What a bucket means, in one line (BRIEF §1.7's rules in words): the Company header's case when there is no card to
 * quote, and the Candidates view's line under its title. */
export function bucketLine(bucket: string | null | undefined): string {
  switch (bucket) {
    case "candidate":
      return "Two kinds of evidence agree, and the price hasn't caught up yet.";
    case "early":
      return "Two kinds of evidence are starting to agree. Worth watching for more.";
    case "watch":
      return "One kind of evidence at full strength, nothing against it, and the price hasn't followed. A name to research, not yet to act on.";
    case "priced_in":
      return "Strong evidence, but the price has already caught up.";
    case "excluded":
      return "Left out this week: a hard red flag.";
    case "none":
      return "No strong evidence this week.";
    default:
      return "Not scored yet.";
  }
}

/** Markdown text as one plain line: the citations out, the whitespace collapsed. */
export function plainText(md: string): string {
  return md.replace(CITE, "").replace(/\s+/g, " ").replace(/\s+([.,;:])/g, "$1").trim();
}

/** A card's case in one line: its summary, else its first paragraph without the citations; null without a card. */
export function caseLine(json: unknown, md: string | null | undefined): string | null {
  const summary = typeof json === "object" && json !== null ? (json as { summary?: unknown }).summary : undefined;
  if (typeof summary === "string" && summary.trim() !== "") return plainText(summary);
  const body = stripTitle(md ?? "").trim();
  if (body === "" || body.startsWith("#")) return null;
  const para = body.split(/\n\s*\n/)[0] ?? "";
  if (/^\s*([-*|>]|\d+\.)/.test(para)) return null; // a list or a table, not a sentence
  const line = plainText(para);
  return line === "" ? null : line;
}

/** A family's name in the Evidence bar's legend; behaviour says who acted (insiders, funds or both). */
export function familyWord(family: string, counted: readonly string[] = []): string {
  switch (family) {
    case "fundamentals":
      return "Business";
    case "behavior":
      return counted.includes("S8") && !counted.includes("S7") ? "Funds" : counted.includes("S8") ? "Insiders and funds" : "Insiders";
    case "text":
      return "Text facts";
    case "structural":
      return "Special situation";
    case "cycle":
      return "Cycle";
    default:
      return label(FAMILY_LABEL, family);
  }
}

const COUNT_WORD = ["no", "one", "two", "three", "four", "five"];

/** The one-family cap (and the soft red flags) in a few words, beside "Evidence 72": "two kinds agree, so no cap". */
export function capShort(b: Breakdown): string {
  const kinds = b.families.filter((f) => f.contribution > 0).length;
  const base =
    kinds === 0
      ? "no signal fired"
      : kinds >= MIN_FAMILIES
        ? `${COUNT_WORD[kinds] ?? kinds} kinds agree, so no cap`
        : b.capped
          ? `one kind only, so capped at ${SINGLE_FAMILY_CAP}`
          : `one kind only; the cap at ${SINGLE_FAMILY_CAP} doesn't bind`;
  return b.softFlags === 0 ? base : `${base}; red flags take ${SOFT_FLAG_PENALTY * b.softFlags} off`;
}

/** One line from a fired signal's stored inputs ("Cash from operations is 3.9× net income, up from 1.8× a year ago."),
 * or its everyday description when the inputs don't say enough. */
export function signalLine(id: string, inputs: Record<string, unknown> | null | undefined): string {
  const i = inputs ?? {};
  const x = (k: string) => n(i[k]);
  const at = (k: string, end: boolean) => {
    const v = i[k];
    return Array.isArray(v) ? n(end ? v[v.length - 1] : v[0]) : n(v);
  };
  const said = ((): string | null => {
    switch (id) {
      case "S1": {
        const [cov, was, gap] = [x("coverage"), x("coverage_year_ago"), at("gaps", false)];
        if (cov !== null && was !== null) return `The order book is ${times(cov)} a year's sales, up from ${times(was)} a year ago.`;
        return gap !== null ? `Orders grew ${Number((gap * 100).toFixed(0))} points faster than sales last quarter.` : null;
      }
      case "S2": {
        const [inc, roic] = [x("inc_roic"), x("roic")];
        if (inc === null) return null;
        return roic !== null ? `New capital earns ${pc(inc)}, against ${pc(roic)} on all of it.` : `New capital earns ${pc(inc)}.`;
      }
      case "S3": {
        const [opm, was, gr, go] = [x("opm"), x("opm_year_ago"), x("g_revenue"), x("g_opex")];
        if (opm !== null && was !== null) return `Operating margin ${pc(opm)}, up from ${pc(was)} a year ago.`;
        return gr !== null && go !== null ? `Sales grew ${pc(gr)} while costs grew ${pc(go)}.` : null;
      }
      case "S4": {
        const [ccr, was] = [x("ccr"), x("ccr_year_ago")];
        if (ccr === null) return null;
        return `Cash from operations is ${times(ccr)} net income${was !== null ? `, up from ${times(was)} a year ago` : ""}.`;
      }
      case "S5": {
        const s = x("share_change_yoy");
        if (i.path_b === true) return "Share issuance stopped after two years of growth.";
        return s !== null && s < 0 ? `Share count down ${pc(-s)} in a year.` : null;
      }
      case "S6": {
        const [now, past] = [x("current"), x("past_max")];
        return now !== null && past !== null ? `Net debt / EBITDA down to ${times(now)} from ${times(past)}.` : null;
      }
      case "S7": {
        const [k, usd, p, inr] = [x("insiders"), x("total_usd"), x("promoter_buyers"), x("total_inr")];
        if (k !== null && k > 0 && usd !== null) return `${k === 1 ? "One insider" : `${k} insiders`} bought ${money(usd, "USD")} of stock.`;
        if (p !== null && p > 0 && inr !== null) return `${p === 1 ? "One promoter" : `${p} promoters`} bought ${money(inr, "INR")} of stock.`;
        const drop = x("pledge_drop_pp");
        return drop !== null ? `Promoter pledge down ${drop.toFixed(1)} points.` : null;
      }
      case "S8": {
        const [h, q, f, r] = [at("holders", true), at("qoq", true), x("fii_dii_pct"), x("rise_pp")];
        if (h !== null && q !== null) return `${Math.round(h)} funds hold it, up ${pc(q)} in a quarter.`;
        return f !== null && r !== null ? `Funds hold ${f.toFixed(1)}%, up ${r.toFixed(1)} points in two quarters.` : null;
      }
      case "S9": {
        const c = x("count");
        if (c === null || c <= 0) return null;
        return c === 1 ? "One fact in its filings, checked word for word." : `${c} facts in its filings, each checked word for word.`;
      }
      case "S10": {
        const ev = Array.isArray(i.events) ? String(i.events[0] ?? "") : "";
        const kind = ev.split(":")[0] ?? "";
        if (kind !== "") return `A recent ${humanize(kind).toLowerCase()}.`;
        return i.holdco === true ? "A listed holding company." : null;
      }
      case "S12": {
        return typeof i.sector === "string" && i.sector !== "" ? `The ${i.sector} cycle is turning up.` : null;
      }
      default:
        return null;
    }
  })();
  return said ?? SIGNAL_PLAIN[id] ?? SIGNAL_NAME[id] ?? id;
}

const MISSING_WORDS: Record<string, string> = {
  history: "not enough price history yet",
  multiples: "no valuation multiple",
  return_52w: "no 52-week price history",
  population: "too few names to compare with",
  roic_above_discount: "its return on capital is below the discount rate",
  value_creating_growth: "its growth doesn't earn more than its cost of capital",
};

/** A Gap part in one line: what it found ("EV/Sales 2.2: cheaper than 87% of its own history."), or why it has no
 * score ("Not scored: not enough price history yet."). */
export function gapLine(p: Pick<GapPart, "id" | "score" | "row">): string {
  const i = p.row?.inputs ?? {};
  if (p.score === null) {
    if (p.row === null) return "Not scored: not computed this week.";
    const m = i.missing;
    const words = Array.isArray(m) && m.length > 0 ? m.map((k) => MISSING_WORDS[String(k)] ?? humanize(String(k)).toLowerCase()).join("; ") : "no score";
    return `Not scored: ${words}.`;
  }
  switch (p.id) {
    case "C1": {
      for (const [key, name] of [
        ["ev_sales", "EV/Sales"],
        ["ev_ebit", "EV/EBIT"],
      ] as const) {
        const [v, q] = [n(i[key]), n(i[`pct_${key}`])];
        if (v === null || q === null) continue;
        const cheaper = Math.round(100 - q);
        return cheaper >= 50
          ? `${name} ${v.toFixed(1)}: cheaper than ${cheaper}% of its own history.`
          : `${name} ${v.toFixed(1)}: dearer than ${Math.round(q)}% of its own history.`;
      }
      return "Its valuation against its own history.";
    }
    case "C2": {
      const [ge, gs] = [n(i.g_e), n(i.g_star)];
      return ge !== null && gs !== null ? `The evidence supports ${pc(ge)} growth; the price implies ${pc(gs)}.` : "The growth the evidence supports, against what the price implies.";
    }
    case "C3": {
      const ret = n(i.return_52w) ?? n(p.row?.value);
      if (ret === null) return "Its 52-week return against the market's.";
      const move = `${ret >= 0 ? "Up" : "Down"} ${pc(Math.abs(ret))} in a year`;
      const rank = n(p.row?.pct);
      if (rank === null) return `${move}.`;
      const where = rank < 50 ? `bottom ${Math.max(1, Math.round(rank))}%` : `top ${Math.max(1, Math.round(100 - rank))}%`;
      const pop = n(i.population);
      return `${move}: ${where}${pop !== null ? ` of ${Math.round(pop)} names` : ""}.`;
    }
  }
}

// ------------------------------------------------------------------------------------------------ kill criteria

const OP_SHORT: Record<string, string> = { "<": "under", "<=": "at or under", ">": "over", ">=": "at or over", "==": "equal to" };

export interface KillLike {
  metric: string;
  operator: string;
  threshold: number | string | null;
  baseline?: number | string | null;
}

/** A kill criterion as one checklist line: "TTM revenue growth under 5.0%". */
export function killRule(k: KillLike): string {
  const { unit } = killMetric(k.metric);
  const cond =
    k.operator === "changes"
      ? `changes${k.baseline === null || k.baseline === undefined ? "" : ` from ${metricValue(k.baseline, unit)}`}`
      : `${OP_SHORT[k.operator] ?? k.operator} ${metricValue(k.threshold, unit)}`;
  return `${killName(k.metric)} ${cond}`;
}

export const KILL_WORD: Record<string, string> = { ok: "safe", triggered: "triggered", unknown: "no verdict yet" };

/** Where a kill criterion stands: "Now 24.0% · safe"; "Not checked yet" before its first check. */
export function killNow(k: { metric: string; status: string; last_value: number | string | null }): string {
  if (k.last_value === null || k.last_value === undefined) return k.status === "triggered" ? "Triggered" : "Not checked yet";
  return `Now ${metricValue(k.last_value, killMetric(k.metric).unit)} · ${KILL_WORD[k.status] ?? k.status}`;
}

// ------------------------------------------------------------------------------------------------ insiders

export interface InsiderEvent {
  event_date: string;
  filed_at?: string | null;
  person: string;
  role?: string | null;
  kind: string;
  value?: number | string | null;
  currency?: string | null;
  planned?: boolean | null;
  source_url?: string | null;
  amends?: string | null;
}

const ET_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });

/** The EDGAR filing day (Eastern) of a filed_at timestamp. */
function filedDay(at: string | null | undefined): string {
  if (!at) return "";
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at.slice(0, 10) : ET_DAY.format(d);
}

function indian(e: InsiderEvent): boolean {
  return e.kind.startsWith("promoter_") || e.kind.startsWith("pledge_");
}

/** The events a reader counts, as pipeline/signals/insiders.py latest_versions takes them (simplified for display): a
 * Form 4/A (`amends` = the original's filing day) replaces that person's same-day original filings that share a trade
 * date with it (all of that day's when none does), the latest amendment winning; an Indian disclosure revised for the
 * same person, trade date and kind keeps only its latest filing. */
export function latestInsiderEvents<E extends InsiderEvent>(events: readonly E[]): E[] {
  const amendments = new Map<string, E[]>(); // person|amends -> the latest amendment filing's rows
  for (const e of events) {
    if (!e.amends) continue;
    const key = `${e.person}|${e.amends}`;
    const have = amendments.get(key);
    if (have !== undefined && have[0]!.source_url === e.source_url) have.push(e);
    else if (have === undefined || (e.filed_at ?? "") > (have[0]!.filed_at ?? "")) amendments.set(key, [e]);
  }
  const replaced = (e: E): boolean => {
    const day = filedDay(e.filed_at);
    const am = amendments.get(`${e.person}|${day}`);
    if (am === undefined) return false;
    const dates = new Set(am.map((a) => a.event_date));
    const sameDay = events.filter((o) => !o.amends && !indian(o) && o.person === e.person && filedDay(o.filed_at) === day);
    const sharing = new Set(sameDay.filter((o) => dates.has(o.event_date)).map((o) => o.source_url ?? ""));
    return sharing.size === 0 || sharing.has(e.source_url ?? "");
  };
  const latest = new Map<string, string>(); // India: person|trade date|kind -> the latest filed_at
  for (const e of events.filter(indian)) {
    const key = `${e.person}|${e.event_date}|${e.kind}`;
    if ((e.filed_at ?? "") >= (latest.get(key) ?? "")) latest.set(key, e.filed_at ?? "");
  }
  return events.filter((e) => {
    if (e.amends) return amendments.get(`${e.person}|${e.amends}`)?.includes(e) ?? false;
    if (indian(e)) return (e.filed_at ?? "") === latest.get(`${e.person}|${e.event_date}|${e.kind}`);
    return !replaced(e);
  });
}

export interface InsiderGroup {
  total: number;
  currency: string;
  people: { who: string; role: string; value: number }[]; // most money first
  from: string;
  to: string;
  planned: number; // trades under a plan made in advance (10b5-1)
  trades: number;
}

const BUY = new Set(["open_market_buy", "promoter_buy"]);
const SELL = new Set(["open_market_sell", "promoter_sell"]);

function groupOf(list: readonly InsiderEvent[], fallback: string): InsiderGroup | null {
  if (list.length === 0) return null;
  const by = new Map<string, { who: string; role: string; value: number }>();
  for (const e of list) {
    const p = by.get(e.person) ?? { who: e.person, role: e.role ?? "", value: 0 };
    p.value += n(e.value) ?? 0;
    if (!p.role && e.role) p.role = e.role;
    by.set(e.person, p);
  }
  const dates = list.map((e) => e.event_date).sort();
  return {
    total: [...by.values()].reduce((t, p) => t + p.value, 0),
    currency: (list.find((e) => e.currency)?.currency ?? fallback).toUpperCase(),
    people: [...by.values()].sort((a, b) => b.value - a.value || a.who.localeCompare(b.who)),
    from: dates[0]!,
    to: dates[dates.length - 1]!,
    planned: list.filter((e) => e.planned === true).length,
    trades: list.length,
  };
}

/** Days between two yyyy-mm-dd dates. */
function days(a: string, b: string): number {
  return Math.round((Date.parse(`${b.slice(0, 10)}T00:00:00Z`) - Date.parse(`${a.slice(0, 10)}T00:00:00Z`)) / 86_400_000);
}

/** The insiders' buying and selling as bars: each side's trades in the year up to its latest one, summed by person
 * (amended filings counted once). Pledges and other events are left to the details list. */
export function insiderSummary(events: readonly InsiderEvent[], fallbackCurrency = "USD"): { bought: InsiderGroup | null; sold: InsiderGroup | null } {
  const counted = latestInsiderEvents(events);
  const side = (kinds: ReadonlySet<string>) => {
    const list = counted.filter((e) => kinds.has(e.kind));
    const last = list.map((e) => e.event_date).sort().at(-1);
    return groupOf(
      list.filter((e) => last !== undefined && days(e.event_date, last) <= 365),
      fallbackCurrency,
    );
  };
  return { bought: side(BUY), sold: side(SELL) };
}

/** When a group's trades happened: "On Sep 15, 2026" or "Jul 3 – Sep 15, 2026". */
export function whenLine(g: Pick<InsiderGroup, "from" | "to">): string {
  if (g.from === g.to) return `On ${shortDate(g.to, true)}`;
  return `${shortDate(g.from, g.from.slice(0, 4) !== g.to.slice(0, 4))} – ${shortDate(g.to, true)}`;
}

/** lib/data.ts insiders() reads a company's latest 25 insider filings of every kind (tests/explain.test.ts pins it). */
export const INSIDER_ROWS = 25;

/** Whether that read hit its cap, so older trades of the year may be missing from the sums. */
export function insidersCapped(rows: number): boolean {
  return rows >= INSIDER_ROWS;
}

/** A side's total as the headline says it: "$510K", or "at least $1.2M" when the read was capped. */
export function insiderTotal(g: Pick<InsiderGroup, "total" | "currency">, capped: boolean): string {
  return `${capped ? "at least " : ""}${money(g.total, g.currency)}`;
}

// ------------------------------------------------------------------------------------------------ charts and cards

/** A chart's last value against a year (four quarters) before: "+12% over a year", "Up 3.1 points over a year",
 * "1.8× a year ago"; null without both values. */
export function trendNote(values: readonly (number | null | undefined)[], format: ChartFormat): string | null {
  let last = -1;
  values.forEach((v, i) => {
    if (typeof v === "number" && Number.isFinite(v)) last = i;
  });
  const now = last >= 0 ? values[last] : undefined;
  const then = last >= 4 ? values[last - 4] : undefined;
  if (typeof now !== "number" || typeof then !== "number" || !Number.isFinite(then)) return null;
  switch (format) {
    case "money":
    case "big": {
      if (then <= 0) return null;
      const ch = now / then - 1;
      if (Math.abs(ch) < 0.0005) return "Flat over a year"; // as the pct branch says it, not "+0%" (PR 6 final review C11)
      return `${ch >= 0 ? "+" : "−"}${pc(Math.abs(ch))} over a year`;
    }
    case "pct": {
      const d = (now - then) * 100;
      return Math.abs(d) < 0.05 ? "Flat over a year" : `${d > 0 ? "Up" : "Down"} ${Math.abs(d).toFixed(1)} points over a year`;
    }
    case "x":
      return `${minus(then.toFixed(1))}× a year ago`;
    case "num":
      return `${minus(then.toFixed(0))} a year ago`;
  }
}

/** A card cut into its "## " sections (Facts, Why it may be mispriced, Risks, ...): the text before the first one is
 * the lead. Sections with nothing under them are left out. Pass the card without its "# title" (lib/cards.ts
 * stripTitle). */
export function cardSections(md: string): { lead: string; sections: { title: string; body: string }[] } {
  const lead: string[] = [];
  const sections: { title: string; body: string[] }[] = [];
  for (const line of md.split("\n")) {
    const h = /^##\s+(.*?)\s*#*\s*$/.exec(line);
    if (h) sections.push({ title: h[1]!.trim(), body: [] });
    else (sections.at(-1)?.body ?? lead).push(line);
  }
  return {
    lead: lead.join("\n").trim(),
    sections: sections.map((s) => ({ title: s.title, body: s.body.join("\n").trim() })).filter((s) => s.body !== ""),
  };
}

// ------------------------------------------------------------------------------------------------ theses

/** What a thesis row asks of you, or where it stands. */
export function thesisAsk(t: { state: string; author: string; card_md: string }): string {
  if (t.state === "research" && t.author === "manual" && t.card_md.trim() === "") return "Card queued for Sunday";
  switch (t.state) {
    case "research":
      return "Card ready: accept it or pass";
    case "review":
      return "A review waits for your verdict";
    case "thesis":
      return "Watching its kill criteria";
    case "position":
      return "Position open";
    case "closed":
      return "Closed";
    case "dismissed":
      return "Dismissed";
    default:
      return humanize(t.state);
  }
}

/** The Theses screen's one line: "2 need you, 3 being watched." */
export function thesesLine(needs: number, watching: number): string {
  if (needs === 0 && watching === 0) return "Nothing open right now.";
  if (needs === 0) return `Nothing needs you; ${watching} being watched.`;
  return `${needs} ${needs === 1 ? "needs" : "need"} you, ${watching} being watched.`;
}
