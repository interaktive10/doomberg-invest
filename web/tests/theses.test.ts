import { describe, expect, it } from "vitest";
import { needsKillReview } from "@/lib/reviews";
import { acceptable, afterVerdict, canMove, cardQueued, group, killTally, markMoved, positionOpen, STATES, verdicts } from "@/lib/theses";

describe("thesis workflow (BRIEF §1.8)", () => {
  it("offers each move in its state only", () => {
    expect(canMove("research", "accept")).toBe(true);
    expect(canMove("thesis", "accept")).toBe(false);
    expect(canMove("research", "dismiss")).toBe(true);
    expect(canMove("thesis", "start_position")).toBe(true);
    expect(canMove("research", "start_position")).toBe(false);
    for (const s of ["thesis", "position", "review"] as const) expect(canMove(s, "close")).toBe(true);
    for (const s of ["research", "closed", "dismissed"] as const) expect(canMove(s, "close")).toBe(false);
  });

  it("knows whether a position is open from the journal", () => {
    const e = (action: string, entry_date: string) => ({ action, entry_date, created_at: `${entry_date}T10:00:00Z` });
    expect(positionOpen([])).toBe(false);
    expect(positionOpen([e("note", "2026-09-01"), e("start_position", "2026-09-02")])).toBe(true);
    expect(positionOpen([e("exit", "2026-09-20"), e("start_position", "2026-09-02"), e("add", "2026-09-10")])).toBe(false);
  });

  it("moves a review back to position or thesis unless it is broken", () => {
    expect(afterVerdict("review", "intact", true)).toBe("position");
    expect(afterVerdict("review", "weakened", false)).toBe("thesis");
    expect(afterVerdict("review", "broken", true)).toBe("review");
    expect(afterVerdict("position", "intact", true)).toBe("position");
  });
});

describe("theses moved to Review in this render", () => {
  it("show their new state without a second read (CI: a re-read in the same render returned the old state)", () => {
    const list = [
      { id: "a", state: "thesis" as const },
      { id: "b", state: "position" as const },
    ];
    const shown = markMoved(list, new Set(["a"]));
    expect(shown.map((t) => t.state)).toEqual(["review", "position"]);
    expect(list[0]?.state).toBe("thesis");
    expect(markMoved(list, new Set())).toEqual(list);
  });
});

describe("accepting a card (§1.8; M7 review R1-F2)", () => {
  const card = { state: "research" as const, author: "routine", card_md: "# Echo", validation: { ok: true } };
  it("only a validated card can be accepted", () => {
    expect(acceptable(card)).toBe(true);
    expect(acceptable({ ...card, author: "manual", card_md: "", validation: {} })).toBe(false);
    expect(acceptable({ ...card, card_md: "  " })).toBe(false);
    expect(acceptable({ ...card, validation: { ok: false } })).toBe(false);
    expect(acceptable({ ...card, validation: null })).toBe(false);
    expect(acceptable({ ...card, state: "thesis" })).toBe(false);
  });
});

describe("leaving Review (§1.8; M7 review R1-F9)", () => {
  it("leaves Review only when no review is pending", () => {
    expect(afterVerdict("review", "intact", true, 1)).toBe("review");
    expect(afterVerdict("review", "intact", true, 0)).toBe("position");
    expect(afterVerdict("review", "weakened", false)).toBe("thesis");
    expect(afterVerdict("review", "broken", false, 0)).toBe("review");
  });
});

describe("a broken verdict keeps the thesis in Review (§1.8; M7 review R2-F3)", () => {
  // two quarters arrived together, so their reviews share created_at; the verdicts come in either order
  const q2 = (verdict: string | null) => ({ period_end: "2026-03-31", verdict, created_at: "2026-09-25T18:24:37Z" });
  const q3 = (verdict: string | null) => ({ period_end: "2026-06-30", verdict, created_at: "2026-09-25T18:24:37Z" });

  it("Q3 broken, then Q2 intact: the thesis stays in Review", () => {
    const first = verdicts([q2(null), q3("broken")]);
    expect(afterVerdict("review", "broken", false, first.pending, first.broken)).toBe("review");
    const then = verdicts([q2("intact"), q3("broken")]);
    expect(then).toEqual({ pending: 0, broken: true });
    expect(afterVerdict("review", "intact", false, then.pending, then.broken)).toBe("review");
    expect(afterVerdict("review", "intact", false, 0, false)).toBe("thesis");
  });

  it("no kill-criteria review for a broken thesis, whichever order the tied reviews are read in", () => {
    expect(needsKillReview("review", [q2("intact"), q3("broken")])).toBe(false);
    expect(needsKillReview("review", [q3("broken"), q2("intact")])).toBe(false);
    expect(needsKillReview("review", [q3("intact"), q2("intact")])).toBe(true);
  });
});

describe("the Theses screen's three groups (overhaul PR 4)", () => {
  it("Needs you, Watching and Closed cover every state once", () => {
    expect(STATES.map((s) => [s, group({ state: s, author: "routine", card_md: "# Card" })])).toEqual([
      ["research", "needs"],
      ["thesis", "watching"],
      ["position", "watching"],
      ["review", "needs"],
      ["closed", "closed"],
      ["dismissed", "closed"],
    ]);
  });

  it("a research entry whose card is queued is Watching, labelled 'card queued', until the routine fills it (PR 5)", () => {
    const waiting = { state: "research" as const, author: "manual", card_md: "" };
    expect(cardQueued(waiting)).toBe(true);
    expect(group(waiting)).toBe("watching");
    // filled in place by the routine: a card to accept or dismiss
    expect(group({ ...waiting, author: "routine", card_md: "# Card" })).toBe("needs");
    expect(cardQueued({ ...waiting, author: "fallback", card_md: "# Card" })).toBe(false);
    // dismissed before the card came: Closed, not queued
    expect(cardQueued({ ...waiting, state: "dismissed" })).toBe(false);
    expect(group({ ...waiting, state: "dismissed" })).toBe("closed");
  });

  it("counts the kill criteria as 'n of m triggered'", () => {
    expect(killTally([])).toBe("none");
    expect(killTally(["ok", "unknown"])).toBe("0 of 2 triggered");
    expect(killTally(["triggered", "ok", "triggered"])).toBe("2 of 3 triggered");
  });
});
