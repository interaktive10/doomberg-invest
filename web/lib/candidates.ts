// The Candidates rules (overhaul PR 4), pure so tests/candidates.test.ts covers them. Both the NEW badge and the
// Evidence change read the same scores rows: the company's rows of the 12 weeks before the shown week. A dismissal
// (candidate_actions) holds until the evidence changes: a signal or a family fires that didn't on the dismissal's
// week, or Evidence moves 10 or more from that week's, in any scored week since; after that the name stays shown. No
// migration: everything is read from stored rows.

import { shortDate } from "@/lib/dates";
import { BOARD_LABEL, bucketLine } from "@/lib/explain";
import { RED_FLAG_NAME } from "@/lib/labels";

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

/** The companies among `rows` (the shown week's scores) that a dismissal still hides: lib/data.ts dismissals() for
 * those rows, the shown week included in the weeks since. Candidates hides them (unless asked to show them) and Home's
 * On the board leaves them out, so the two screens count the same names. */
export function stillDismissed(
  rows: readonly { company_id: string; evidence: number | string; families: string[]; fired_signals: string[] }[],
  held: ReadonlyMap<string, { baseline: Baseline | null; since: readonly Baseline[] }>,
): Set<string> {
  return new Set(
    rows
      .filter((r) => {
        const d = held.get(r.company_id);
        return d !== undefined && dismissalHolds(d.baseline, [...d.since, { evidence: r.evidence, families: r.families, signals: r.fired_signals }]);
      })
      .map((r) => r.company_id),
  );
}

/** "+3.5", "−2.0", "0.0" (a true minus sign, like the rest of the app's figures). */
export function signed(d: number): string {
  return d > 0 ? `+${d.toFixed(1)}` : d < 0 ? `−${Math.abs(d).toFixed(1)}` : "0.0";
}

// ---------------------------------------------------------------- the cards' words (overhaul PR 6)

export type ShownBucket = "candidate" | "early" | "priced_in";

const SHOWN: readonly ShownBucket[] = ["candidate", "early", "priced_in"];

/** The three views, named as every screen names the buckets (lib/explain.ts BOARD_LABEL): Candidate is "On the board". */
export const BUCKET_TABS: readonly [ShownBucket, string][] = SHOWN.map((b) => [b, BOARD_LABEL[b] ?? b]);

/** Each view's one line under the title: what the bucket means, as the Company header says it. */
export const BUCKET_LINE = Object.fromEntries(SHOWN.map((b) => [b, bucketLine(b)])) as Record<ShownBucket, string>;

/** What the legend says each score needs in this view (the bucket rules: Evidence 60+ with Gap 50+ on the board,
 * Evidence 40-59 in Early, Gap under 50 once priced in). */
export const BUCKET_RANGE: Record<ShownBucket, { evidence: string; gap: string }> = {
  candidate: { evidence: "60+", gap: "50+" },
  early: { evidence: "40–59", gap: "50+" },
  priced_in: { evidence: "60+", gap: "under 50" },
};

export const BUCKET_EMPTY: Record<ShownBucket, string> = {
  candidate: "Nothing on the board this week.",
  early: "Nothing in Early this week.",
  priced_in: "Nothing priced in this week.",
};

/** The Evidence change as a card says it, after the word "Evidence": "+4.1 since Sep 11" (up), "−3.4 since Sep 11"
 * (down), "unchanged since Sep 11", or "has no earlier score" (none in the 12 weeks before). */
export function evidenceMove(c: { change: number; since: string } | null): { tone: "up" | "down" | "flat"; text: string } {
  if (c === null) return { tone: "flat", text: "has no earlier score" };
  if (c.change === 0) return { tone: "flat", text: `unchanged since ${shortDate(c.since)}` };
  return { tone: c.change > 0 ? "up" : "down", text: `${signed(c.change)} since ${shortDate(c.since)}` };
}

/** A card's safety line: "No red flags", or the flags by name ("Watch out: ...") in amber, red when one is hard. The
 * codes (R1-R6) stay for the tooltip. */
export function flagLine(flags: readonly string[], hard: boolean): { tone: "good" | "warn" | "bad"; text: string; codes: string } {
  if (flags.length === 0) return { tone: "good", text: "No red flags", codes: "" };
  return { tone: hard ? "bad" : "warn", text: `Watch out: ${flags.map((f) => RED_FLAG_NAME[f] ?? f).join("; ")}`, codes: flags.join(", ") };
}
