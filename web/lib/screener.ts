import { z } from "zod";

// Mirrors pipeline/screener.py ScreenSpec: the JSON `screen(spec)` takes (db/migrations/0007).
export const METRICS = [
  "revenue_ttm", "revenue_yoy", "opm", "roic", "fcf_ttm", "ccr", "nd_to_ebitda", "share_change_yoy", "market_cap",
  "ev", "return_52w",
] as const;
export const BUCKETS = ["candidate", "priced_in", "early", "excluded", "none"] as const;
export const FAMILIES = ["fundamentals", "behavior", "text", "structural", "capex", "cycle"] as const;
export const SIGNALS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12"] as const;

export const MetricFilter = z
  .object({ metric: z.enum(METRICS), op: z.enum([">=", "<=", ">", "<"]), value: z.number().finite() })
  .strict();

export const ScreenSpec = z
  .object({
    market: z.enum(["us", "in"]).optional(),
    capex_desk: z.boolean().optional(),
    sector: z.string().min(1).optional(),
    buckets: z.array(z.enum(BUCKETS)).min(1).optional(),
    min_evidence: z.number().min(0).max(100).optional(),
    min_gap: z.number().min(0).max(100).optional(),
    signals_any: z.array(z.enum(SIGNALS)).min(1).optional(),
    families_all: z.array(z.enum(FAMILIES)).min(1).optional(),
    exclude_hard_flags: z.boolean().optional(),
    metrics: z.array(MetricFilter).optional(),
    limit: z.number().int().min(1).max(2000).optional(),
  })
  .strict();

export type ScreenSpec = z.infer<typeof ScreenSpec>;

/** A submitted form or a query string (FormData and URLSearchParams both fit). */
export interface FormLike {
  get(name: string): FormDataEntryValue | null;
  getAll(name: string): FormDataEntryValue[];
}

const num = (v: FormDataEntryValue | null): number | undefined => {
  if (v === null || String(v).trim() === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
};

/** The filter builder's form (or its query string) -> a validated spec (empty fields are left out); throws a ZodError
 * on a value outside the contract. */
export function specFromForm(form: FormLike): ScreenSpec {
  const pick = (name: string): string | undefined => {
    const v = form.get(name);
    return v === null || String(v) === "" ? undefined : String(v);
  };
  const list = (name: string): string[] => form.getAll(name).map(String).filter((x) => x !== "");
  const metrics = [0, 1, 2]
    .map((i) => ({ metric: pick(`metric_${i}`), op: pick(`op_${i}`), value: num(form.get(`value_${i}`)) }))
    .filter((m) => m.metric !== undefined && m.op !== undefined && m.value !== undefined);
  const raw: Record<string, unknown> = {
    market: pick("market"),
    capex_desk: pick("capex_desk") === undefined ? undefined : pick("capex_desk") === "true",
    sector: pick("sector"),
    buckets: list("buckets").length ? list("buckets") : undefined,
    min_evidence: num(form.get("min_evidence")),
    min_gap: num(form.get("min_gap")),
    signals_any: list("signals_any").length ? list("signals_any") : undefined,
    families_all: list("families_all").length ? list("families_all") : undefined,
    exclude_hard_flags: form.get("exclude_hard_flags") === "on" ? true : undefined,
    metrics: metrics.length ? metrics : undefined,
    limit: num(form.get("limit")),
  };
  for (const k of Object.keys(raw)) if (raw[k] === undefined) delete raw[k];
  return ScreenSpec.parse(raw);
}

/** A spec back to the builder's query string (the inverse of specFromForm), for links, saved screens and CSV export. */
export function specToQuery(spec: ScreenSpec): URLSearchParams {
  const q = new URLSearchParams();
  if (spec.market) q.set("market", spec.market);
  if (spec.capex_desk !== undefined) q.set("capex_desk", String(spec.capex_desk));
  if (spec.sector) q.set("sector", spec.sector);
  for (const b of spec.buckets ?? []) q.append("buckets", b);
  if (spec.min_evidence !== undefined) q.set("min_evidence", String(spec.min_evidence));
  if (spec.min_gap !== undefined) q.set("min_gap", String(spec.min_gap));
  for (const s of spec.signals_any ?? []) q.append("signals_any", s);
  for (const f of spec.families_all ?? []) q.append("families_all", f);
  if (spec.exclude_hard_flags) q.set("exclude_hard_flags", "on");
  (spec.metrics ?? []).slice(0, 3).forEach((m, i) => {
    q.set(`metric_${i}`, m.metric);
    q.set(`op_${i}`, m.op);
    q.set(`value_${i}`, String(m.value));
  });
  if (spec.limit !== undefined) q.set("limit", String(spec.limit));
  return q;
}

/** The screener's CSV columns (personal use, BRIEF §6). */
export const CSV_COLUMNS = [
  "name", "market", "ticker", "nse_symbol", "sector", "industry", "capex_desk", "week_end", "bucket", "evidence", "gap",
  "families", "fired_signals", "red_flags", "hard_flag", "c1", "c2", "c3", "c4", ...METRICS, "company_id",
] as const;

/** A screener row with its metrics spread into columns. */
export function csvRow<T extends { metrics: Record<string, number | null> }>(r: T): Record<string, unknown> {
  return { ...r, ...Object.fromEntries(METRICS.map((m) => [m, r.metrics[m] ?? null])) };
}
