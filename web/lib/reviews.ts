// BRIEF §4.9 "Reviews: after each new quarterly filing for a thesis or position company, the web app creates a review
// with the pack diff since the last review", and §1.8 Review (a kill criterion that triggers moves a thesis there
// too, pipeline/thesis/kill_criteria.py). Pure, so tests/reviews.test.ts covers it; lib/data.ts reads the rows and
// writes the reviews.

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

/** The state a review compares against: read from the card's pack, or stored with the review before. */
export interface Snapshot {
  as_of: string; // yyyy-mm-dd
  quarter: string | null; // the latest quarter end known then
  figures: Record<string, number | null>; // that quarter's key figures
  signals: string[]; // fired signal ids
  red_flags: string[]; // fired red-flag ids
  context: Record<string, number | null>; // C1..C4, evidence, gap
  kill: Record<string, number | null>; // kill metric id -> value
}

export interface NewFact {
  id: string;
  subject: string;
  value: number | null;
  unit: string;
  as_of: string; // the date the quote states, else the document's
  published_at: string | null; // when its document was published: what makes it new (M7 review R2-F2)
  quote: string;
  url: string | null;
}

export interface NewItems {
  facts: NewFact[];
  ownership: Record<string, unknown>[];
  insiders: Record<string, unknown>[];
}

/** What changed since the last review (or the card's pack): M7 review R1-F4. */
export interface StateDiff {
  since: string | null; // the as_of of the state compared against
  signals: { fired: string[]; dropped: string[] };
  red_flags: { fired: string[]; dropped: string[] };
  context: { id: string; before: number | null; now: number | null }[];
  kill: { metric: string; before: number | null; now: number | null }[];
  facts: NewFact[];
  ownership: Record<string, unknown>[];
  insiders: Record<string, unknown>[];
}

export interface PackDiff {
  kind: "quarter" | "kill_criteria";
  since: string | null; // the last quarter the thesis had seen
  quarters: FilingRow[]; // the new quarter (one per review); none for a kill-criteria review
  figures: { name: string; before: number | null; now: number | null }[]; // the quarter before -> this one
  kill_criteria: KillSnapshot[]; // the criteria as they stand
  state: StateDiff | null; // with the latest review of a batch
  snapshot: Snapshot | null; // the state now, what the next review compares against
}

export const FIGURES = ["revenue", "op_income", "net_income", "cfo", "rpo", "diluted_shares"] as const;
const CONTEXT_ORDER = ["C1", "C2", "C3", "C4", "evidence", "gap"];

function num(x: unknown): number | null {
  const n = typeof x === "number" ? x : typeof x === "string" && x.trim() !== "" ? Number(x) : Number.NaN;
  return Number.isFinite(n) ? n : null;
}

function records(x: unknown): Record<string, unknown>[] {
  return Array.isArray(x) ? x.filter((i): i is Record<string, unknown> => typeof i === "object" && i !== null) : [];
}

/** The latest quarter end among the pack's metrics (evidence_pack.metrics[].period_end), if any. */
export function packQuarter(pack: Record<string, unknown>): string | null {
  let best: string | null = null;
  for (const m of records(pack.metrics)) {
    const pe = m.period_end;
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

/** The card's pack as a Snapshot (null for a pack without a week, such as a manual research entry). */
export function packSnapshot(pack: Record<string, unknown>): Snapshot | null {
  if (typeof pack.week_end !== "string") return null;
  const quarter = packQuarter(pack);
  const figures: Record<string, number | null> = {};
  for (const m of records(pack.metrics)) {
    if (typeof m.name === "string" && m.period_end === quarter && (FIGURES as readonly string[]).includes(m.name)) {
      figures[m.name] = num(m.value);
    }
  }
  const signals: string[] = [];
  const flags: string[] = [];
  for (const s of records(pack.signals)) {
    if (s.fired !== true) continue;
    const id = String(s.id ?? "").replace(/^s:/, "");
    (s.kind === "red_flag" ? flags : signals).push(id);
  }
  const context: Record<string, number | null> = {};
  for (const c of records(pack.context)) context[String(c.id ?? "").replace(/^c:/, "")] = num(c.value);
  const kill: Record<string, number | null> = {};
  for (const k of records(pack.kill_metrics)) kill[String(k.id)] = num(k.value);
  return { as_of: pack.week_end, quarter, figures, signals: signals.sort(), red_flags: flags.sort(), context, kill };
}

/** A company's rows from signal_values, redflag_values and context_values (week_end, id, and the fired flag, the
 * inputs or the value). */
export interface WeekRows {
  signals: readonly { week_end: string; signal_id: string; fired: boolean }[];
  flags: readonly { week_end: string; flag_id: string; inputs: Record<string, unknown> | null }[];
  context: readonly { week_end: string; metric_id: string; value: unknown }[];
}

/** The fired signals, fired red flags and context of the latest scored week (scores.week_end; M7 review R2-F1). The
 * weekly run stores a red flag only when it fired or is unknown (pipeline/signals/weekly.py), so a scored week without
 * a flag's row is a week the flag was clear: the latest week that has any row would show a cleared flag as firing. */
export function scoredWeek(week: string | null, rows: WeekRows): Pick<Snapshot, "signals" | "red_flags" | "context"> {
  const at = <T extends { week_end: string }>(list: readonly T[]): T[] => list.filter((r) => r.week_end === week);
  const context: Record<string, number | null> = {};
  for (const c of at(rows.context)) context[c.metric_id] = num(c.value);
  return {
    signals: at(rows.signals).filter((r) => r.fired).map((r) => r.signal_id).sort(),
    red_flags: at(rows.flags).filter((r) => r.inputs?.status === "fired").map((r) => r.flag_id).sort(),
    context,
  };
}

/** The snapshot stored with the most recent review that has one. */
export function lastSnapshot(reviews: readonly { created_at: string; snapshot?: unknown }[]): Snapshot | null {
  const withOne = reviews.filter((r) => typeof r.snapshot === "object" && r.snapshot !== null);
  const last = [...withOne].sort((a, b) => a.created_at.localeCompare(b.created_at)).pop();
  return last ? (last.snapshot as Snapshot) : null;
}

function ordered(ids: Iterable<string>): string[] {
  const rank = (id: string) => {
    const i = CONTEXT_ORDER.indexOf(id);
    return i === -1 ? CONTEXT_ORDER.length : i;
  };
  return [...new Set(ids)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** The first day a row is new to a state as of `since` (yyyy-mm-dd): the next day, since a state as of a week end
 * has what was published or filed by the end of that day (pipeline/db/pit.py cutoff_for; M7 review R2-F2). */
export function dayAfter(since: string): string {
  const d = new Date(`${since.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** What changed between `before` and `now`: signals and red flags that started or stopped firing, context before ->
 * now, the kill criteria's metrics before -> now (M7 review R1-F4), and the facts whose document was published after
 * `before` (the pack's rule, whatever period they are about; M7 review R2-F2) and the ownership rows and insider
 * events filed after it. */
export function stateDiff(before: Snapshot | null, now: Snapshot, items: NewItems): StateDiff {
  const minus = (a: readonly string[], b: readonly string[]) => a.filter((x) => !b.includes(x));
  const since = before?.as_of ?? null;
  const after = (d: unknown) => since === null || (typeof d === "string" && d.slice(0, 10) > since);
  return {
    since,
    signals: { fired: minus(now.signals, before?.signals ?? []), dropped: minus(before?.signals ?? [], now.signals) },
    red_flags: {
      fired: minus(now.red_flags, before?.red_flags ?? []),
      dropped: minus(before?.red_flags ?? [], now.red_flags),
    },
    context: ordered([...Object.keys(before?.context ?? {}), ...Object.keys(now.context)]).map((id) => ({
      id,
      before: before?.context[id] ?? null,
      now: now.context[id] ?? null,
    })),
    kill: Object.keys(now.kill)
      .sort()
      .map((metric) => ({ metric, before: before?.kill[metric] ?? null, now: now.kill[metric] ?? null })),
    facts: items.facts.filter((f) => after(f.published_at)),
    ownership: items.ownership.filter((o) => after(o.filed_at)),
    insiders: items.insiders.filter((e) => after(e.filed_at)),
  };
}

/** The reviews to create for the quarters filed after `since` (§4.9): one per quarter (M7 review R1-F9), each with its
 * figures against the quarter before it; the latest also carries what changed since `before` and the snapshot the
 * next review compares against. */
export function quarterReviews(
  rows: readonly FilingRow[],
  since: string | null,
  before: Snapshot | null,
  now: Snapshot,
  kills: readonly KillSnapshot[],
  items: NewItems,
): PackDiff[] {
  const sorted = [...rows].sort((a, b) => a.period_end.localeCompare(b.period_end));
  const fresh = sorted.filter((r) => since === null || r.period_end > since);
  return fresh.map((q, i) => {
    const prev = sorted.filter((r) => r.period_end < q.period_end).pop();
    const last = i === fresh.length - 1;
    return {
      kind: "quarter",
      since: i > 0 ? (fresh[i - 1]?.period_end ?? since) : since,
      quarters: [{ ...q }],
      figures: FIGURES.map((name) => ({
        name,
        before: prev ? prev[name] : (before?.figures[name] ?? null),
        now: q[name],
      })),
      kill_criteria: kills.map((k) => ({ ...k })),
      state: last ? stateDiff(before, now, items) : null,
      snapshot: last ? now : null,
    };
  });
}

/** A thesis in Review with no review waiting for a verdict needs one (M7 review R1-F1): a kill criterion moved it
 * there without a new quarter. Not after a "broken" verdict on any of its reviews, which keeps a thesis in Review until
 * it is closed; reviews made together share created_at, so "the last verdict" would depend on the order read (M7
 * review R2-F3). */
export function needsKillReview(state: string, reviews: readonly { verdict: string | null }[]): boolean {
  return state === "review" && !reviews.some((r) => r.verdict === null || r.verdict === "broken");
}

/** The review for a thesis a kill criterion moved to Review: no new quarter, the criteria as they stand, and what
 * changed since `before`. */
export function killReview(
  since: string | null,
  before: Snapshot | null,
  now: Snapshot,
  kills: readonly KillSnapshot[],
  items: NewItems,
): PackDiff {
  return {
    kind: "kill_criteria",
    since,
    quarters: [],
    figures: [],
    kill_criteria: kills.map((k) => ({ ...k })),
    state: stateDiff(before, now, items),
    snapshot: now,
  };
}
