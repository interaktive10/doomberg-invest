import "server-only";
import { cache } from "react";
import { db } from "@/lib/supabase/admin";
import { allPages } from "@/lib/paging";
import type { Baseline, ScorePoint } from "@/lib/candidates";
import type { LabPricesRun } from "@/lib/lab";
import type { ScreenSpec } from "@/lib/screener";
import type { SearchHit } from "@/lib/search";
import { firingTimeline, type ContextRow, type SignalRow } from "@/lib/why";
import type { QuarterRow, SeriesPoint } from "@/lib/metrics";
import {
  dayAfter,
  FIGURES,
  killReview,
  lastSnapshot,
  needsKillReview,
  packSnapshot,
  quarterReviews,
  reviewedThrough,
  scoredWeek,
  type FilingRow,
  type KillSnapshot,
  type NewItems,
  type Snapshot,
} from "@/lib/reviews";

// Server-side reads for the screens (BRIEF §6). Point-in-time tables are read only through the *_display_v views
// (db/migrations/0003; the guard's pit_rule); everything else through service_role.

export type Bucket = "candidate" | "priced_in" | "early" | "excluded" | "none";
export type ThesisState = "research" | "thesis" | "position" | "review" | "closed" | "dismissed";

export interface ScreenerRow {
  company_id: string;
  market: "us" | "in";
  name: string;
  ticker: string | null;
  nse_symbol: string | null;
  sector: string | null;
  industry: string | null;
  week_end: string;
  evidence: number;
  gap: number | null;
  families: string[];
  bucket: Bucket;
  fired_signals: string[];
  red_flags: string[];
  hard_flag: boolean;
}

export interface Company {
  id: string;
  market: "us" | "in";
  name: string;
  ticker: string | null;
  nse_symbol: string | null;
  cik: string | null;
  isin: string | null;
  sector: string | null;
  industry: string | null;
  in_universe: boolean;
  excluded_reason: string | null;
  fiscal_year_end: string | null;
}

export interface Thesis {
  id: string;
  company_id: string;
  state: ThesisState;
  card_md: string;
  card_json: Card | Record<string, never>;
  evidence_pack: Record<string, unknown>;
  author: "routine" | "fallback" | "manual";
  validation: Record<string, unknown>;
  created_week: string;
  next_review: string | null;
  accepted_at: string | null;
  dismissed_reason: string | null;
  updated_at: string;
  companies?: Pick<Company, "name" | "market" | "ticker" | "nse_symbol" | "fiscal_year_end"> | null;
}

export interface Card {
  summary?: string;
  facts?: { text: string; cites: string[] }[];
  why_mispriced?: { text: string; cites: string[] }[];
  inferences?: string[];
  assumptions?: string[];
  risks?: { text: string; cites: string[] }[];
  kill_criteria?: { metric_id: string; operator: string; threshold: number | null; check_after: string; why: string }[];
  read_next?: { title: string; url: string }[];
}

export interface KillCriterion {
  id: string;
  metric: string;
  operator: string;
  threshold: number | null;
  check_after: string;
  status: "ok" | "triggered" | "unknown";
  last_value: number | null;
  last_checked: string | null;
  baseline: number | null;
  why: string | null;
  triggered_week: string | null;
}

export interface Review {
  id: string;
  thesis_id: string;
  period_end: string | null;
  pack_diff: Record<string, unknown>;
  verdict: "intact" | "weakened" | "broken" | null;
  note: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface JournalEntry {
  id: string;
  thesis_id: string | null;
  entry_date: string;
  action: "note" | "start_position" | "add" | "trim" | "exit" | "review";
  portfolio_pct: number | null;
  reason: string;
  override_reason: string | null;
  created_at: string;
}

export interface Postmortem {
  thesis_id: string;
  what_happened: string;
  thesis_right: boolean | null;
  signals_right: Record<string, unknown> | null;
  lessons: string;
  created_at: string;
}

function rows<T>(res: { data: unknown; error: { message: string } | null }): T[] {
  if (res.error) throw new Error(res.error.message);
  return (res.data ?? []) as T[];
}

function one<T>(res: { data: unknown; error: { message: string } | null }): T | null {
  if (res.error) throw new Error(res.error.message);
  return (res.data ?? null) as T | null;
}

// ---------------------------------------------------------------- Home

export async function latestDigest(): Promise<{ week_end: string; title: string; body_md: string } | null> {
  return one(await db().from("digests").select("week_end, title, body_md").order("week_end", { ascending: false })
    .limit(1).maybeSingle());
}

export interface SourceHealth {
  source: string;
  last_success: string | null;
  last_error: string | null;
  stale: boolean;
}

export async function sourceHealth(): Promise<SourceHealth[]> {
  return rows(await db().from("source_health").select("source, last_success, last_error, stale").order("source"));
}

export interface LlmUse {
  provider: string;
  calls: number;
  ok: number;
  rateLimited: number;
  tokensIn: number;
  tokensOut: number;
}

/** Settings' LLM calls by provider over the last 7 days, counted in the database (the llm_use_7d view, migration
 * 0011): PostgREST returns at most max_rows rows, so counting fetched rows undercounts a busy week (M7 review R1-F6).
 * The digest no longer lists LLM use (overhaul PR 5). */
export async function llmUse(): Promise<LlmUse[]> {
  const data = rows<{ provider: string; calls: number; ok: number; rate_limited: number; tokens_in: number; tokens_out: number }>(
    await db().from("llm_use_7d").select("provider, calls, ok, rate_limited, tokens_in, tokens_out").order("provider"),
  );
  return data.map((r) => ({
    provider: r.provider,
    calls: Number(r.calls),
    ok: Number(r.ok),
    rateLimited: Number(r.rate_limited),
    tokensIn: Number(r.tokens_in),
    tokensOut: Number(r.tokens_out),
  }));
}

// ---------------------------------------------------------------- Candidates

/** screen(spec) rows up to spec.limit (the SQL function's default is 500), a page at a time (lib/paging.ts). */
export async function screen(spec: ScreenSpec): Promise<ScreenerRow[]> {
  return allPages<ScreenerRow>((from, to) => db().rpc("screen", { p: spec }).range(from, to), spec.limit ?? 500);
}

type PageQuery = (from: number, to: number) => PromiseLike<{ data: unknown; error: { message: string } | null }>;

/** A read filtered on a list of ids, 100 ids per request (the URL stays short) and a page at a time (max_rows). */
async function byIds<T>(ids: readonly string[], query: (chunk: string[]) => PageQuery): Promise<T[]> {
  const out: T[] = [];
  for (let i = 0; i < ids.length; i += 100) out.push(...(await allPages<T>(query(ids.slice(i, i + 100)), 1_000_000)));
  return out;
}

/** The companies' scores rows in [from, before): what the NEW badge and the Evidence change read (lib/candidates.ts). */
export async function scoreHistory(ids: readonly string[], from: string, before: string): Promise<Map<string, ScorePoint[]>> {
  const data = await byIds<ScorePoint & { company_id: string }>(ids, (chunk) => (a, b) =>
    db().from("scores").select("company_id, week_end, evidence, bucket").in("company_id", chunk).gte("week_end", from)
      .lt("week_end", before).order("company_id").order("week_end").range(a, b)); // prettier-ignore
  const out = new Map<string, ScorePoint[]>();
  for (const r of data) out.set(r.company_id, [...(out.get(r.company_id) ?? []), r]);
  return out;
}

/** Each company's latest dismissal (candidate_actions) with what it was dismissed on (that week's Evidence, families
 * and fired signals) and the same for every scored week after it through `week` (lib/candidates.ts dismissalHolds
 * reads them all: once a week releases the hold it stays released). A dismissal without a scores row for its week has
 * no baseline (null). The reads cover only the dismissed companies, from their own dismissal week on. */
export async function dismissals(ids: readonly string[], week: string): Promise<Map<string, { week_end: string; reason: string | null; baseline: Baseline | null; since: Baseline[] }>> {
  const acts = await byIds<{ company_id: string; week_end: string; reason: string | null }>(ids, (chunk) => (a, b) =>
    db().from("candidate_actions").select("company_id, week_end, reason").in("company_id", chunk).eq("action", "dismiss")
      .order("created_at", { ascending: false }).order("id").range(a, b)); // prettier-ignore
  const latest = new Map<string, { week_end: string; reason: string | null }>();
  for (const x of acts) if (!latest.has(x.company_id)) latest.set(x.company_id, { week_end: x.week_end, reason: x.reason });
  if (latest.size === 0) return new Map();
  // one pair of reads per dismissal week, each for the companies dismissed that week, from that week through `week`
  const groups = new Map<string, string[]>();
  for (const [id, d] of latest) groups.set(d.week_end, [...(groups.get(d.week_end) ?? []), id]);
  type Scored = { company_id: string; week_end: string; evidence: number | string; families: string[] };
  type Fired = { company_id: string; week_end: string; signal_id: string };
  const reads = await Promise.all(
    [...groups].map(([from, who]) =>
      Promise.all([
        byIds<Scored>(who, (chunk) => (a, b) =>
          db().from("scores").select("company_id, week_end, evidence, families").in("company_id", chunk)
            .gte("week_end", from).lte("week_end", week).order("company_id").order("week_end").range(a, b)), // prettier-ignore
        byIds<Fired>(who, (chunk) => (a, b) =>
          db().from("signal_values").select("company_id, week_end, signal_id").in("company_id", chunk)
            .gte("week_end", from).lte("week_end", week).eq("fired", true).order("company_id").order("week_end")
            .order("signal_id").range(a, b)), // prettier-ignore
      ]),
    ),
  );
  const scored = reads.flatMap(([s]) => s);
  const fired = reads.flatMap(([, f]) => f);
  const at = (r: Scored): Baseline => ({
    evidence: r.evidence,
    families: r.families,
    signals: fired.filter((f) => f.company_id === r.company_id && f.week_end === r.week_end).map((f) => f.signal_id),
  });
  const out = new Map<string, { week_end: string; reason: string | null; baseline: Baseline | null; since: Baseline[] }>();
  for (const [id, d] of latest) {
    const mine = scored.filter((r) => r.company_id === id);
    const s = mine.find((r) => r.week_end === d.week_end);
    out.set(id, { ...d, baseline: s ? at(s) : null, since: mine.filter((r) => r.week_end > d.week_end).map(at) });
  }
  return out;
}

export async function latestThesisByCompany(ids: string[]): Promise<Map<string, Pick<Thesis, "id" | "state" | "author">>> {
  if (ids.length === 0) return new Map();
  const data = rows<{ id: string; company_id: string; state: ThesisState; author: Thesis["author"]; created_week: string }>(
    await db().from("theses").select("id, company_id, state, author, created_week").in("company_id", ids)
      .order("created_week", { ascending: false }),
  );
  const out = new Map<string, Pick<Thesis, "id" | "state" | "author">>();
  for (const t of data) if (!out.has(t.company_id)) out.set(t.company_id, { id: t.id, state: t.state, author: t.author });
  return out;
}

// ---------------------------------------------------------------- Company

/** Cached per request: the page and its tab title (generateMetadata) read the same row once. */
export const company = cache(async (id: string): Promise<Company | null> => {
  return one(await db().from("companies").select(
    "id, market, name, ticker, nse_symbol, cik, isin, sector, industry, in_universe, excluded_reason, fiscal_year_end",
  ).eq("id", id).maybeSingle());
});

/** The company's latest scores row (BRIEF §4.8): Evidence, Gap, bucket, families and the weights version used. */
export async function latestScore(id: string): Promise<{ week_end: string; evidence: number; gap: number | null; families: string[]; bucket: Bucket; weights_version: string } | null> {
  return one(await db().from("scores").select("week_end, evidence, gap, families, bucket, weights_version").eq("company_id", id)
    .order("week_end", { ascending: false }).limit(1).maybeSingle());
}

export interface WhyData {
  signals: SignalRow[]; // the scored week's signal rows
  weeks: string[]; // every week with a scores row or any signal row, through the scored week (lib/why.ts firingTimeline)
  fired: Map<string, Set<string>>; // signal -> the weeks it fired, through the scored week
  flags: { flag_id: string; hard: boolean; inputs: Record<string, unknown> | null }[]; // fired in the scored week
  context: ContextRow[];
  weights: Record<string, unknown> | null; // the weights version the score used
  lab: LabResult[]; // the latest Lab run, for each signal's verdict (lib/lab.ts)
}

/** What "Why this score" reads for the company's scored week (overhaul PR 5): that week's signal, red-flag and context
 * rows, the weeks each signal fired (for "firing since"), the weights version and the latest Lab run. Point-in-time:
 * nothing after the scored week. */
export async function whyScore(id: string, score: { week_end: string; weights_version: string }): Promise<WhyData> {
  const week = score.week_end;
  const [signals, history, scored, flags, context, version, lab] = await Promise.all([
    db().from("signal_values").select("signal_id, fired, strength, inputs").eq("company_id", id).eq("week_end", week)
      .order("signal_id"),
    allPages<{ week_end: string; signal_id: string; fired: boolean }>((a, b) =>
      db().from("signal_values").select("week_end, signal_id, fired").eq("company_id", id).lte("week_end", week)
        .order("week_end").order("signal_id").range(a, b), 1_000_000), // prettier-ignore
    allPages<{ week_end: string }>((a, b) =>
      db().from("scores").select("week_end").eq("company_id", id).lte("week_end", week).order("week_end").range(a, b), 1_000_000),
    db().from("redflag_values").select("flag_id, hard, inputs").eq("company_id", id).eq("week_end", week)
      .eq("inputs->>status", "fired").order("flag_id"),
    db().from("context_values").select("metric_id, value, pct, inputs").eq("company_id", id).eq("week_end", week)
      .order("metric_id"),
    db().from("weights_versions").select("weights").eq("version", score.weights_version).maybeSingle(),
    labResults(),
  ]);
  return {
    signals: rows<SignalRow>(signals),
    ...firingTimeline(scored.map((w) => w.week_end), history),
    flags: rows(flags),
    context: rows<ContextRow>(context),
    weights: one<{ weights: Record<string, unknown> }>(version)?.weights ?? null,
    lab,
  };
}

// ---------------------------------------------------------------- Search

const HIT = "id, market, name, ticker, nse_symbol";

/** The search box's reads (lib/search.ts parseSearch gives the escaped patterns): companies whose code is the query,
 * and up to `limit` whose ticker or name contains it. Each is its own ilike filter: no .or() string is built from the
 * query. */
export async function searchCompanies(exact: string, contains: string, limit: number): Promise<{ exact: SearchHit[]; hits: SearchHit[] }> {
  const [byTicker, bySymbol, inTicker, inName] = await Promise.all([
    db().from("companies").select(HIT).ilike("ticker", exact).limit(2),
    db().from("companies").select(HIT).ilike("nse_symbol", exact).limit(2),
    db().from("companies").select(HIT).ilike("ticker", contains).order("ticker").limit(limit),
    db().from("companies").select(HIT).ilike("name", contains).order("name").limit(limit),
  ]);
  return {
    exact: [...rows<SearchHit>(byTicker), ...rows<SearchHit>(bySymbol)],
    hits: [...rows<SearchHit>(byTicker), ...rows<SearchHit>(bySymbol), ...rows<SearchHit>(inTicker), ...rows<SearchHit>(inName)],
  };
}

/** The latest scored week (null before the first) and each listed company's Evidence and bucket in it. */
export async function scoresInLatestWeek(ids: readonly string[]): Promise<{ week: string | null; scores: Map<string, { evidence: number | string; bucket: Bucket }> }> {
  const latest = one<{ week_end: string }>(
    await db().from("scores").select("week_end").order("week_end", { ascending: false }).limit(1).maybeSingle(),
  );
  const out = new Map<string, { evidence: number | string; bucket: Bucket }>();
  if (latest === null || ids.length === 0) return { week: latest?.week_end ?? null, scores: out };
  const data = rows<{ company_id: string; evidence: number | string; bucket: Bucket }>(
    await db().from("scores").select("company_id, evidence, bucket").in("company_id", [...ids]).eq("week_end", latest.week_end),
  );
  for (const r of data) out.set(r.company_id, { evidence: r.evidence, bucket: r.bucket });
  return { week: latest.week_end, scores: out };
}

export async function fundamentals(id: string): Promise<(QuarterRow & { currency: string | null; filed_at: string })[]> {
  return rows(await db().from("fundamentals_display_v").select(
    "period_end, filed_at, revenue, op_income, net_income, pretax_income, tax_expense, cfo, capex, da, total_assets, " +
      "cash, total_debt, equity, rpo, diluted_shares, shares_outstanding, currency",
  ).eq("company_id", id).order("period_end"));
}

/** The Company page's chart series: company_series, written by the weekly signals run (M7 review R1-F5). */
export async function companySeries(id: string): Promise<{ week_end: string; points: SeriesPoint[] } | null> {
  return one(await db().from("company_series").select("week_end, points").eq("company_id", id).maybeSingle());
}

export async function insiders(id: string): Promise<Record<string, unknown>[]> {
  return rows(await db().from("insider_events_display_v").select(
    "id, event_date, filed_at, person, role, kind, shares, value, currency, planned, source_url, amends",
  ).eq("company_id", id).order("event_date", { ascending: false }).limit(25));
}

export async function events(id: string): Promise<Record<string, unknown>[]> {
  return rows(await db().from("corp_events_display_v").select("id, event_date, filed_at, kind, detail, source_url")
    .eq("company_id", id).neq("kind", "announcement").order("event_date", { ascending: false }).limit(25));
}

export interface FactRow {
  id: string;
  fact_type: string;
  subject_key: string;
  value_num: number | null;
  value_low: number | null;
  value_high: number | null;
  unit: string;
  period_label: string | null;
  as_of: string;
  quote: string;
  documents: { url: string; kind: string; published_at: string; title: string | null } | null;
  companies: Pick<Company, "name" | "market" | "ticker" | "nse_symbol"> | null;
}

export async function facts(companyIds: string[], limit = 30): Promise<(FactRow & { company_id: string })[]> {
  if (companyIds.length === 0) return [];
  return rows(await db().from("facts").select(
    "id, company_id, fact_type, subject_key, value_num, value_low, value_high, unit, period_label, as_of, quote, " +
      "documents(url, kind, published_at, title), companies(name, market, ticker, nse_symbol)",
  ).in("company_id", companyIds).eq("verification_status", "verified").order("as_of", { ascending: false })
    .limit(limit));
}

export async function thesesOf(companyId: string): Promise<Pick<Thesis, "id" | "state" | "created_week" | "author">[]> {
  return rows(await db().from("theses").select("id, state, created_week, author").eq("company_id", companyId)
    .order("created_week", { ascending: false }));
}

// ---------------------------------------------------------------- Theses and the journal

export async function theses(): Promise<Thesis[]> {
  return rows(await db().from("theses").select(
    "id, company_id, state, card_md, card_json, evidence_pack, author, validation, created_week, next_review, " +
      "accepted_at, dismissed_reason, updated_at, companies(name, market, ticker, nse_symbol, fiscal_year_end)",
  ).order("updated_at", { ascending: false }));
}

/** For the Theses list: each thesis's Evidence at its card's week and now (the latest scored week), and its kill
 * criteria's statuses. A company without a scores row in that week has none (null). */
export async function thesisFigures(list: readonly Pick<Thesis, "id" | "company_id" | "created_week">[]): Promise<Map<string, { atCard: number | null; now: number | null; kills: KillCriterion["status"][] }>> {
  const out = new Map<string, { atCard: number | null; now: number | null; kills: KillCriterion["status"][] }>();
  if (list.length === 0) return out;
  const latest = one<{ week_end: string }>(
    await db().from("scores").select("week_end").order("week_end", { ascending: false }).limit(1).maybeSingle(),
  );
  const companies = [...new Set(list.map((t) => t.company_id))];
  const weeks = [...new Set([...list.map((t) => t.created_week), ...(latest ? [latest.week_end] : [])])];
  const [scored, kills] = await Promise.all([
    byIds<{ company_id: string; week_end: string; evidence: number | string }>(companies, (chunk) => (a, b) =>
      db().from("scores").select("company_id, week_end, evidence").in("company_id", chunk).in("week_end", weeks)
        .order("company_id").order("week_end").range(a, b)), // prettier-ignore
    byIds<{ thesis_id: string; status: KillCriterion["status"] }>(list.map((t) => t.id), (chunk) => (a, b) =>
      db().from("kill_criteria").select("thesis_id, status").in("thesis_id", chunk).order("thesis_id").order("id")
        .range(a, b)), // prettier-ignore
  ]);
  const at = (company: string, week: string | undefined) => {
    const r = week === undefined ? undefined : scored.find((x) => x.company_id === company && x.week_end === week);
    return r === undefined ? null : number(r.evidence);
  };
  for (const t of list) {
    out.set(t.id, {
      atCard: at(t.company_id, t.created_week),
      now: at(t.company_id, latest?.week_end),
      kills: kills.filter((k) => k.thesis_id === t.id).map((k) => k.status),
    });
  }
  return out;
}

/** A thesis page's tab title: its company's name and code (not cached: the page's own reads must see the moves its
 * server actions make in the same request). */
export async function thesisTitle(id: string): Promise<Pick<Company, "name" | "market" | "ticker" | "nse_symbol"> | null> {
  const t = one<{ companies: Pick<Company, "name" | "market" | "ticker" | "nse_symbol"> | null }>(
    await db().from("theses").select("companies(name, market, ticker, nse_symbol)").eq("id", id).maybeSingle(),
  );
  return t?.companies ?? null;
}

export async function thesis(id: string): Promise<Thesis | null> {
  return one(await db().from("theses").select(
    "id, company_id, state, card_md, card_json, evidence_pack, author, validation, created_week, next_review, " +
      "accepted_at, dismissed_reason, updated_at, companies(name, market, ticker, nse_symbol, fiscal_year_end)",
  ).eq("id", id).maybeSingle());
}

export async function killCriteria(thesisId: string): Promise<KillCriterion[]> {
  return rows(await db().from("kill_criteria").select(
    "id, metric, operator, threshold, check_after, status, last_value, last_checked, baseline, why, triggered_week",
  ).eq("thesis_id", thesisId).order("metric"));
}

export async function reviews(thesisId: string): Promise<Review[]> {
  return rows(await db().from("reviews").select("id, thesis_id, period_end, pack_diff, verdict, note, created_at, decided_at")
    .eq("thesis_id", thesisId).order("created_at", { ascending: false })
    .order("period_end", { ascending: false, nullsFirst: false })); // a batch shares created_at: newest quarter first
}

export async function journal(thesisId?: string): Promise<JournalEntry[]> {
  let q = db().from("journal").select("id, thesis_id, entry_date, action, portfolio_pct, reason, override_reason, created_at");
  if (thesisId) q = q.eq("thesis_id", thesisId);
  return rows(await q.order("created_at", { ascending: false }).limit(500));
}

export async function postmortems(): Promise<Postmortem[]> {
  return rows(await db().from("postmortems").select("thesis_id, what_happened, thesis_right, signals_right, lessons, created_at")
    .order("created_at", { ascending: false }));
}

export async function postmortem(thesisId: string): Promise<Postmortem | null> {
  return one(await db().from("postmortems").select("thesis_id, what_happened, thesis_right, signals_right, lessons, created_at")
    .eq("thesis_id", thesisId).maybeSingle());
}

interface ReviewState {
  period_end: string | null;
  verdict: string | null;
  created_at: string;
  snapshot: unknown;
}

// A select of its own, not reviews(): the page reads reviews() after ensureReviews, and Next memoizes a repeated GET
// within a render, so the page would not see the reviews made here.
async function reviewStates(thesisId: string): Promise<ReviewState[]> {
  return rows(await db().from("reviews").select("period_end, verdict, created_at, snapshot:pack_diff->snapshot")
    .eq("thesis_id", thesisId));
}

function number(x: unknown): number | null {
  const n = typeof x === "number" ? x : typeof x === "string" && x !== "" ? Number(x) : Number.NaN;
  return Number.isFinite(n) ? n : null;
}

/** The company's state now, for a review (M7 review R1-F4): the latest quarter's figures; the latest scored week's
 * fired signals, red flags, context and scores (lib/reviews.ts scoredWeek, M7 review R2-F1); and the kill criteria's
 * latest values. It is as of that week, like a card's pack, so the next review lists what was published after it,
 * including what arrived after this review was made (M7 review R2-F2). */
async function stateNow(companyId: string, filed: FilingRow[], kills: KillCriterion[]): Promise<Snapshot> {
  const score = one<{ week_end: string; evidence: unknown; gap: unknown }>(
    await db().from("scores").select("week_end, evidence, gap").eq("company_id", companyId)
      .order("week_end", { ascending: false }).limit(1).maybeSingle(),
  );
  const week = score?.week_end ?? null;
  const none = Promise.resolve({ data: [], error: null }); // never scored: no signals, flags or context yet
  const [signals, flags, context] = await Promise.all([
    week === null ? none : db().from("signal_values").select("week_end, signal_id, fired").eq("company_id", companyId)
      .eq("week_end", week),
    week === null ? none : db().from("redflag_values").select("week_end, flag_id, inputs").eq("company_id", companyId)
      .eq("week_end", week),
    week === null ? none : db().from("context_values").select("week_end, metric_id, value").eq("company_id", companyId)
      .eq("week_end", week),
  ]);
  const latest = [...filed].sort((a, b) => a.period_end.localeCompare(b.period_end)).pop();
  const figures: Record<string, number | null> = {};
  if (latest) for (const name of FIGURES) figures[name] = latest[name];
  const at = scoredWeek(week, {
    signals: rows<{ week_end: string; signal_id: string; fired: boolean }>(signals),
    flags: rows<{ week_end: string; flag_id: string; inputs: Record<string, unknown> | null }>(flags),
    context: rows<{ week_end: string; metric_id: string; value: unknown }>(context),
  });
  if (score) Object.assign(at.context, { evidence: number(score.evidence), gap: number(score.gap) });
  return {
    as_of: week ?? new Date().toISOString().slice(0, 10),
    quarter: latest?.period_end ?? null,
    figures,
    ...at,
    kill: Object.fromEntries(kills.map((k) => [k.metric, number(k.last_value)])),
  };
}

/** Verified facts whose document was published after `since` (the pack's rule: pipeline/db/thesis_repo.py
 * pack_facts; M7 review R2-F2), newest first, and the ownership rows and insider events filed after it (through the
 * point-in-time views). */
async function itemsSince(companyId: string, since: string | null): Promise<NewItems> {
  const from = since === null ? "1900-01-01" : dayAfter(since);
  const [f, o, i] = await Promise.all([
    db().from("facts").select("id, subject, value_num, unit, as_of, quote, documents!inner(url, published_at)")
      .eq("company_id", companyId).eq("verification_status", "verified").gte("documents.published_at", from)
      .order("documents(published_at)", { ascending: false }).order("as_of", { ascending: false }).limit(50),
    db().from("ownership_display_v").select("quarter_end, filed_at, inst_holders, fii_pct, dii_pct, promoter_pct, " +
      "promoter_pledged_pct").eq("company_id", companyId).gte("filed_at", from).order("filed_at").limit(20),
    db().from("insider_events_display_v").select("event_date, filed_at, person, role, kind, shares, value, currency")
      .eq("company_id", companyId).gte("filed_at", from).order("filed_at").limit(50),
  ]);
  const facts = rows<{ id: string; subject: string; value_num: unknown; unit: string; as_of: string; quote: string;
    documents: { url: string; published_at: string } | null }>(f); // prettier-ignore
  return {
    facts: facts.map((x) => ({ id: x.id, subject: x.subject, value: number(x.value_num), unit: x.unit, as_of: x.as_of,
      published_at: x.documents?.published_at ?? null, quote: x.quote, url: x.documents?.url ?? null })), // prettier-ignore
    ownership: rows<Record<string, unknown>>(o),
    insiders: rows<Record<string, unknown>>(i),
  };
}

/** BRIEF §4.9 Reviews: for each thesis or position whose company has filed quarters the thesis hasn't seen, one
 * review per quarter (the unique index makes a re-render a no-op), and for a thesis a kill criterion moved to Review
 * without a new quarter, one review to record a verdict on (a partial unique index keeps it to one open). A review
 * holds the pack diff since the last one (figures, signals, red flags, context, kill metrics, new facts, ownership
 * and insider events) and the state it saw, and the thesis moves to the Review column until Manzoor marks it (§1.8;
 * M7 review R1-F1, F4, F9). Returns the ids it moved to Review: the page shows their new state with lib/theses.ts
 * markMoved, because reading the rows again in the same render returns the first answer (Next memoizes a repeated
 * GET within a render). */
export async function ensureReviews(list: Pick<Thesis, "id" | "company_id" | "state" | "evidence_pack" | "accepted_at" | "created_week">[]): Promise<Set<string>> {
  const moved = new Set<string>();
  for (const t of list) {
    if (t.state !== "thesis" && t.state !== "position" && t.state !== "review") continue;
    const [filed, revs, kills] = await Promise.all([fundamentals(t.company_id), reviewStates(t.id), killCriteria(t.id)]);
    const rowsFiled: FilingRow[] = filed.map((r) => ({
      period_end: r.period_end, filed_at: r.filed_at, revenue: r.revenue, op_income: r.op_income,
      net_income: r.net_income, cfo: r.cfo, rpo: r.rpo, diluted_shares: r.diluted_shares,
    }));
    const start = t.accepted_at ?? `${t.created_week}T00:00:00Z`;
    const lastQuarter = revs.map((r) => r.period_end).filter((p): p is string => p !== null).sort().pop() ?? null;
    const since = reviewedThrough(lastQuarter, t.evidence_pack, rowsFiled, start);
    const fresh = rowsFiled.some((r) => since === null || r.period_end > since);
    if (!fresh && !needsKillReview(t.state, revs)) continue;
    const before = lastSnapshot(revs) ?? packSnapshot(t.evidence_pack);
    const snap: KillSnapshot[] = kills.map((k) => ({
      metric: k.metric, operator: k.operator, threshold: k.threshold, status: k.status, last_value: k.last_value,
    }));
    const [now, items] = await Promise.all([stateNow(t.company_id, rowsFiled, kills), itemsSince(t.company_id, before?.as_of ?? null)]);
    if (fresh) {
      const made = quarterReviews(rowsFiled, since, before, now, snap, items)
        .map((d) => ({ thesis_id: t.id, period_end: d.quarters[0]?.period_end ?? null, pack_diff: d }));
      const ins = await db().from("reviews").upsert(made, { onConflict: "thesis_id,period_end", ignoreDuplicates: true }).select("id");
      if (ins.error) throw new Error(ins.error.message);
    } else {
      const ins = await db().from("reviews").insert({ thesis_id: t.id, period_end: null, pack_diff: killReview(since, before, now, snap, items) });
      if (ins.error && ins.error.code !== "23505") throw new Error(ins.error.message); // another render made it
    }
    if (t.state !== "review") {
      const up = await db().from("theses").update({ state: "review", updated_at: new Date().toISOString() })
        .eq("id", t.id).in("state", ["thesis", "position"]).select("id");
      if (up.error) throw new Error(up.error.message);
      if ((up.data ?? []).length > 0) moved.add(t.id);
    }
  }
  return moved;
}

export async function setting<T>(key: string, fallback: T): Promise<T> {
  const r = one<{ value: T }>(await db().from("app_settings").select("value").eq("key", key).maybeSingle());
  return r === null ? fallback : r.value;
}

// ---------------------------------------------------------------- Signal Lab and Settings

export interface LabResult {
  run_at: string;
  signal_id: string;
  market: string;
  horizon_m: number;
  period: "in_sample" | "out_of_sample";
  n: number;
  excess_mean: number | null;
  excess_median: number | null;
  hit_rate: number | null;
  p10: number | null;
  t_nw: number | null;
  notes: string | null;
}

export async function labResults(): Promise<LabResult[]> {
  const latest = one<{ run_at: string }>(await db().from("lab_results").select("run_at").order("run_at", { ascending: false })
    .limit(1).maybeSingle());
  if (latest === null) return [];
  const day = latest.run_at.slice(0, 10);
  return rows(await db().from("lab_results").select(
    "run_at, signal_id, market, horizon_m, period, n, excess_mean, excess_median, hit_rate, p10, t_nw, notes",
  ).gte("run_at", `${day}T00:00:00Z`).order("signal_id").order("horizon_m").order("period"));
}

/** The Signal Lab's price download (pipeline/lab/price_history.py): the latest finished lab_prices runs row that
 * recorded its progress (stats.tickers; a run that failed before that is passed over, like repo.latest_run_stats). */
export async function labPricesRun(): Promise<LabPricesRun | null> {
  return one(await db().from("runs").select("started_at, status, error, stats").eq("kind", "lab_prices")
    .not("finished_at", "is", null).not("stats->tickers", "is", null).order("started_at", { ascending: false })
    .limit(1).maybeSingle());
}

export async function weightsVersions(): Promise<{ version: string; weights: Record<string, unknown>; reason: string; approved_by: string | null; approved_at: string | null }[]> {
  return rows(await db().from("weights_versions").select("version, weights, reason, approved_by, approved_at")
    .order("approved_at", { ascending: false, nullsFirst: true }));
}
