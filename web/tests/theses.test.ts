import { describe, expect, it } from "vitest";
import { afterVerdict, canMove, positionOpen } from "@/lib/theses";

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
