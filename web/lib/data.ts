import "server-only";
import { db } from "@/lib/supabase/admin";
import type { ScreenSpec } from "@/lib/screener";
import type { QuarterRow } from "@/lib/metrics";

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
  capex_desk: boolean;
  week_end: string;
  evidence: number;
  gap: number | null;
  families: string[];
  bucket: Bucket;
  fired_signals: string[];
  red_flags: string[];
  hard_flag: boolean;
  c1: number | null;
  c2: number | null;
  c3: number | null;
  c4: number | null;
  metrics: Record<string, number | null>;
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
  capex_desk: boolean;
  in_universe: boolean;
  excluded_reason: string | null;
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
  companies?: Pick<Company, "name" | "market" | "ticker" | "nse_symbol"> | null;
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

export async function llmUse(days = 7): Promise<LlmUse[]> {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const data = rows<{ provider: string; ok: boolean; error: string | null; tokens_in: number | null; tokens_out: number | null }>(
    await db().from("llm_calls").select("provider, ok, error, tokens_in, tokens_out").gte("created_at", since),
  );
  const by = new Map<string, LlmUse>();
  for (const r of data) {
    const u = by.get(r.provider) ?? { provider: r.provider, calls: 0, ok: 0, rateLimited: 0, tokensIn: 0, tokensOut: 0 };
    u.calls += 1;
    u.ok += r.ok ? 1 : 0;
    u.rateLimited += !r.ok && (r.error ?? "").includes(": 429") ? 1 : 0;
    u.tokensIn += r.tokens_in ?? 0;
    u.tokensOut += r.tokens_out ?? 0;
    by.set(r.provider, u);
  }
  return [...by.values()].sort((a, b) => a.provider.localeCompare(b.provider));
}

// ---------------------------------------------------------------- Candidates and the screener

export async function screen(spec: ScreenSpec): Promise<ScreenerRow[]> {
  return rows(await db().rpc("screen", { p: spec }));
}

export async function dismissedThisWeek(week: string): Promise<Set<string>> {
  const data = rows<{ company_id: string }>(
    await db().from("candidate_actions").select("company_id").eq("week_end", week).eq("action", "dismiss"),
  );
  return new Set(data.map((r) => r.company_id));
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

export async function screens(): Promise<{ id: string; name: string; spec: ScreenSpec }[]> {
  return rows(await db().from("screens").select("id, name, spec").order("name"));
}

// ---------------------------------------------------------------- Company

export async function company(id: string): Promise<Company | null> {
  return one(await db().from("companies").select(
    "id, market, name, ticker, nse_symbol, cik, isin, sector, industry, capex_desk, in_universe, excluded_reason",
  ).eq("id", id).maybeSingle());
}

export async function fundamentals(id: string): Promise<(QuarterRow & { currency: string | null })[]> {
  return rows(await db().from("fundamentals_display_v").select(
    "period_end, revenue, op_income, net_income, pretax_income, tax_expense, cfo, capex, da, total_assets, cash, " +
      "total_debt, equity, rpo, diluted_shares, shares_outstanding, currency",
  ).eq("company_id", id).order("period_end"));
}

export async function ownership(id: string): Promise<Record<string, unknown>[]> {
  return rows(await db().from("ownership_display_v").select(
    "quarter_end, filed_at, inst_holders, fii_pct, dii_pct, promoter_pct, promoter_pledged_pct, source",
  ).eq("company_id", id).order("quarter_end", { ascending: false }).limit(8));
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
}

export async function facts(companyIds: string[], limit = 30): Promise<(FactRow & { company_id: string })[]> {
  if (companyIds.length === 0) return [];
  return rows(await db().from("facts").select(
    "id, company_id, fact_type, subject_key, value_num, value_low, value_high, unit, period_label, as_of, quote, " +
      "documents(url, kind, published_at, title)",
  ).in("company_id", companyIds).eq("verification_status", "verified").order("as_of", { ascending: false })
    .limit(limit));
}

export async function signalTimeline(id: string): Promise<{ week_end: string; signal_id: string; strength: number }[]> {
  return rows(await db().from("signal_values").select("week_end, signal_id, strength").eq("company_id", id)
    .eq("fired", true).order("week_end", { ascending: false }).limit(300));
}

export async function contextHistory(id: string): Promise<{ week_end: string; metric_id: string; value: number | null; pct: number | null; inputs: Record<string, unknown> }[]> {
  return rows(await db().from("context_values").select("week_end, metric_id, value, pct, inputs").eq("company_id", id)
    .order("week_end").limit(1000));
}

export async function thesesOf(companyId: string): Promise<Pick<Thesis, "id" | "state" | "created_week" | "author">[]> {
  return rows(await db().from("theses").select("id, state, created_week, author").eq("company_id", companyId)
    .order("created_week", { ascending: false }));
}

// ---------------------------------------------------------------- Theses and the journal

export async function theses(): Promise<Thesis[]> {
  return rows(await db().from("theses").select(
    "id, company_id, state, card_md, card_json, evidence_pack, author, validation, created_week, next_review, " +
      "accepted_at, dismissed_reason, updated_at, companies(name, market, ticker, nse_symbol)",
  ).order("updated_at", { ascending: false }));
}

export async function thesis(id: string): Promise<Thesis | null> {
  return one(await db().from("theses").select(
    "id, company_id, state, card_md, card_json, evidence_pack, author, validation, created_week, next_review, " +
      "accepted_at, dismissed_reason, updated_at, companies(name, market, ticker, nse_symbol)",
  ).eq("id", id).maybeSingle());
}

export async function killCriteria(thesisId: string): Promise<KillCriterion[]> {
  return rows(await db().from("kill_criteria").select(
    "id, metric, operator, threshold, check_after, status, last_value, last_checked, baseline, why, triggered_week",
  ).eq("thesis_id", thesisId).order("metric"));
}

export async function reviews(thesisId: string): Promise<Review[]> {
  return rows(await db().from("reviews").select("id, thesis_id, period_end, pack_diff, verdict, note, created_at, decided_at")
    .eq("thesis_id", thesisId).order("created_at", { ascending: false }));
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

export async function setting<T>(key: string, fallback: T): Promise<T> {
  const r = one<{ value: T }>(await db().from("app_settings").select("value").eq("key", key).maybeSingle());
  return r === null ? fallback : r.value;
}

// ---------------------------------------------------------------- Capex Desk

export interface CapexIndexRow {
  category: string;
  week_end: string;
  value: number | null;
  direction: "rising" | "flat" | "falling";
  input_growth: number | null;
}

export async function capexIndex(): Promise<CapexIndexRow[]> {
  const data = rows<CapexIndexRow>(await db().from("capex_index").select("category, week_end, value, direction, input_growth")
    .order("week_end", { ascending: false }).limit(500));
  const latest = new Map<string, CapexIndexRow>();
  for (const r of data) if (!latest.has(r.category)) latest.set(r.category, r);
  return [...latest.values()].sort((a, b) => a.category.localeCompare(b.category));
}

export interface Membership {
  company_id: string;
  category: string;
  source: "industry_map" | "p06";
  status: "proposed" | "confirmed" | "rejected";
  evidence: string;
  quote: string | null;
  decision_reason: string | null;
  companies: Pick<Company, "name" | "market" | "ticker" | "nse_symbol"> | null;
}

export async function memberships(): Promise<Membership[]> {
  return rows(await db().from("capex_memberships").select(
    "company_id, category, source, status, evidence, quote, decision_reason, companies(name, market, ticker, nse_symbol)",
  ).order("status").order("category").limit(1000));
}

export async function capexDeskIds(): Promise<string[]> {
  return rows<{ id: string }>(await db().from("companies").select("id").eq("capex_desk", true).limit(2000)).map((r) => r.id);
}

export interface GraphEdge {
  from_company_id: string;
  relation: string;
  companies: { name: string } | null;
  entities: { name: string; kind: string } | null;
}

export async function graphEdges(limit = 400): Promise<GraphEdge[]> {
  return rows(await db().from("links").select("from_company_id, relation, companies(name), entities(name, kind)")
    .limit(limit));
}

export async function capexBriefs(): Promise<{ week_end: string; body_md: string }[]> {
  return rows(await db().from("capex_briefs").select("week_end, body_md").order("week_end", { ascending: false }).limit(26));
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

export async function weightsVersions(): Promise<{ version: string; weights: Record<string, unknown>; reason: string; approved_by: string | null; approved_at: string | null }[]> {
  return rows(await db().from("weights_versions").select("version, weights, reason, approved_by, approved_at")
    .order("approved_at", { ascending: false, nullsFirst: true }));
}

export async function universeCounts(): Promise<{ market: string; in_universe: boolean }[]> {
  return rows(await db().from("companies").select("market, in_universe").limit(20000));
}
