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
 * it is closed with a post-mortem; otherwise it goes back to position (an open position) or thesis. */
export function afterVerdict(state: ThesisState, verdict: "intact" | "weakened" | "broken", open: boolean): ThesisState {
  if (state !== "review" || verdict === "broken") return state;
  return open ? "position" : "thesis";
}
