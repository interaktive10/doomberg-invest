// The Candidates rules (overhaul PR 4), pure so tests/candidates.test.ts covers them. Both the NEW badge and the
// Evidence change read the same scores rows: the company's rows of the 12 weeks before the shown week. A dismissal
// (candidate_actions) holds until the evidence changes: a signal or a family fires that didn't on the dismissal's
// week, or Evidence moves 10 or more from that week's, in any scored week since; after that the name stays shown. No
// migration: everything is read from stored rows.

export const NOVELTY_WEEKS = 12;
export const EVIDENCE_MOVE = 10;

export interface ScorePoint {
  week_end: string;
  evidence: number | string;
  bucket: string;
}

export interface Baseline {
  evidence: number | string;
  families: readonly string[];
  signals: readonly string[];
}

/** The first week the NEW badge and the Evidence change look back to: 12 weeks before `week` (ISO dates). */
export function windowStart(week: string): string {
  const d = new Date(`${week}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 7 * NOVELTY_WEEKS);
  return d.toISOString().slice(0, 10);
}

/** NEW: the company is in `bucket` in `week` for the first time in 12 weeks (no row of the 12 weeks before it in the
 * same bucket). */
export function isNew(bucket: string, week: string, history: readonly ScorePoint[]): boolean {
  const from = windowStart(week);
  return !history.some((h) => h.week_end >= from && h.week_end < week && h.bucket === bucket);
}

/** Evidence now minus Evidence in the company's previous scores row (within the 12 weeks), one decimal, with that row's
 * week (a missed weekly run makes it older than last week); null without one. */
export function evidenceChange(evidence: number | string, week: string, history: readonly ScorePoint[]): { change: number; since: string } | null {
  const from = windowStart(week);
  const prev = history.filter((h) => h.week_end >= from && h.week_end < week).sort((a, b) => b.week_end.localeCompare(a.week_end))[0];
  if (prev === undefined) return null;
  const d = Number(evidence) - Number(prev.evidence);
  return Number.isFinite(d) ? { change: Math.round(d * 10) / 10, since: prev.week_end } : null;
}

/** Whether one week's state releases a dismissal made on `then`: a signal or a family fires that didn't on the
 * dismissal's week, or Evidence is 10 or more away from that week's. */
export function releases(then: Baseline, week: Baseline): boolean {
  const newSignal = week.signals.some((s) => !then.signals.includes(s));
  const newFamily = week.families.some((f) => !then.families.includes(f));
  return newSignal || newFamily || Math.abs(Number(week.evidence) - Number(then.evidence)) >= EVIDENCE_MOVE;
}

/** Whether a dismissal still hides the company: no scored week since it (`since`, the current one included) has
 * released it. Once one has, the name stays shown, even if a later week looks like the dismissal's again. A dismissal
 * without its week's scores row (no baseline) doesn't hold. */
export function dismissalHolds(then: Baseline | null, since: readonly Baseline[]): boolean {
  return then !== null && !since.some((w) => releases(then, w));
}

/** "+3.5", "−2.0", "0.0" (a true minus sign, like the rest of the app's figures). */
export function signed(d: number): string {
  return d > 0 ? `+${d.toFixed(1)}` : d < 0 ? `−${Math.abs(d).toFixed(1)}` : "0.0";
}
