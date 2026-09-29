import type { ThesisState } from "@/lib/data";

// BRIEF §1.8 thesis states and the moves the web app offers (Research → Thesis → Position → Review → Closed, plus
// dismissed from research). Pure, so tests/theses.test.ts covers the rules.

export const STATES: readonly ThesisState[] = ["research", "thesis", "position", "review", "closed", "dismissed"];
export const LIVE_STATES = ["research", "thesis", "position", "review"] as const;

export const STATE_LABEL: Record<ThesisState, string> = {
  research: "Research",
  thesis: "Thesis",
  position: "Position",
  review: "Review",
  closed: "Closed",
  dismissed: "Dismissed",
};

export type Move = "accept" | "dismiss" | "start_position" | "close";

export function canMove(state: ThesisState, move: Move): boolean {
  switch (move) {
    case "accept":
    case "dismiss":
      return state === "research";
    case "start_position":
      return state === "thesis";
    case "close":
      return state === "thesis" || state === "position" || state === "review";
  }
}

/** A position is open when the last start_position / exit entry is a start_position. */
export function positionOpen(entries: readonly { action: string; entry_date: string; created_at: string }[]): boolean {
  const moves = entries
    .filter((e) => e.action === "start_position" || e.action === "exit")
    .sort((a, b) => (a.entry_date + a.created_at).localeCompare(b.entry_date + b.created_at));
  return moves.length > 0 && moves[moves.length - 1]?.action === "start_position";
}

/** The state after a review verdict (§1.8 Review: intact / weakened / broken). A broken thesis stays in review until
 * it is closed with a post-mortem, and so does one with another review still waiting for a verdict (M7 review
 * R1-F9) or with a broken verdict on another review, whatever the order the verdicts came in (M7 review R2-F3);
 * otherwise it goes back to position (an open position) or thesis. */
export function afterVerdict(
  state: ThesisState,
  verdict: "intact" | "weakened" | "broken",
  open: boolean,
  stillPending = 0,
  brokenBefore = false,
): ThesisState {
  if (state !== "review" || verdict === "broken" || brokenBefore || stillPending > 0) return state;
  return open ? "position" : "thesis";
}

/** The reviews still waiting for a verdict, and whether any says broken. */
export function verdicts(reviews: readonly { verdict: string | null }[]): { pending: number; broken: boolean } {
  return { pending: reviews.filter((r) => r.verdict === null).length, broken: reviews.some((r) => r.verdict === "broken") };
}

/** Only a card the pipeline wrote and validate.py passed can become a thesis (§1.8: Research is "a card was
 * generated"; Thesis gets "monitoring, kill criteria and review dates"). A manual research entry has no card, pack
 * or kill criteria, so it can be dismissed but not accepted (M7 review R1-F2). */
export function acceptable(t: { state: ThesisState; author: string; card_md: string; validation: unknown }): boolean {
  const v = t.validation;
  const valid = typeof v === "object" && v !== null && (v as { ok?: unknown }).ok === true;
  return t.state === "research" && t.author !== "manual" && t.card_md.trim() !== "" && valid;
}

/** The theses with those in `moved` shown in Review (lib/data.ts ensureReviews moved them in this render). */
export function markMoved<T extends { id: string; state: ThesisState }>(list: readonly T[], moved: ReadonlySet<string>): T[] {
  return list.map((t) => (moved.has(t.id) ? { ...t, state: "review" as const } : t));
}
