// BRIEF §4.9 "Reviews: after each new quarterly filing for a thesis or position company, the web app creates a review
// with the pack diff since the last review." Pure, so tests/reviews.test.ts covers it; lib/data.ts writes the rows.

export interface FilingRow {
  period_end: string;
  filed_at: string;
  revenue: number | null;
  op_income: number | null;
  net_income: number | null;
  cfo: number | null;
  rpo: number | null;
  diluted_shares: number | null;
}

export interface KillSnapshot {
  metric: string;
  operator: string;
  threshold: number | null;
  status: string;
  last_value: number | null;
}

export interface PackDiff {
  since: string | null;
  quarters: FilingRow[];
  kill_criteria: KillSnapshot[];
}

/** The latest quarter end among the pack's metrics (evidence_pack.metrics[].period_end), if any. */
export function packQuarter(pack: Record<string, unknown>): string | null {
  const metrics = Array.isArray(pack.metrics) ? (pack.metrics as unknown[]) : [];
  let best: string | null = null;
  for (const m of metrics) {
    const pe = typeof m === "object" && m !== null ? (m as { period_end?: unknown }).period_end : undefined;
    if (typeof pe === "string" && (best === null || pe > best)) best = pe;
  }
  return best;
}

/** What the thesis already knew: the last review's quarter, else the card's pack, else the latest quarter filed
 * before the thesis started (null: none, so every quarter on file is new). */
export function reviewedThrough(
  lastReview: string | null,
  pack: Record<string, unknown>,
  rows: readonly FilingRow[],
  start: string,
): string | null {
  if (lastReview !== null) return lastReview;
  const fromPack = packQuarter(pack);
  if (fromPack !== null) return fromPack;
  let best: string | null = null;
  for (const r of rows) if (r.filed_at < start && (best === null || r.period_end > best)) best = r.period_end;
  return best;
}

/** The review to create, or null when no quarter after `since` has been filed. */
export function packDiff(rows: readonly FilingRow[], since: string | null, kills: readonly KillSnapshot[]): PackDiff | null {
  const quarters = rows
    .filter((r) => since === null || r.period_end > since)
    .sort((a, b) => a.period_end.localeCompare(b.period_end))
    .map((r) => ({ ...r }));
  if (quarters.length === 0) return null;
  return { since, quarters, kill_criteria: kills.map((k) => ({ ...k })) };
}
