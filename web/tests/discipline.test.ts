import { describe, expect, it } from "vitest";
import { checkStartPosition, thesisWeeks } from "@/lib/discipline";

describe("discipline rule (BRIEF §11.9)", () => {
  const now = new Date("2026-09-25T12:00:00Z");
  it("counts weeks from acceptance, else from the card's week", () => {
    expect(thesisWeeks("2026-08-28T12:00:00Z", "2026-07-03", now)).toBe(4);
    expect(thesisWeeks(null, "2026-09-04", now)).toBe(3);
  });
  it("needs 4 weeks by default, or a written override reason", () => {
    expect(checkStartPosition(4, 4, null)).toEqual({ ok: true, weeks: 4, message: "" });
    const early = checkStartPosition(3, 4, "   ");
    expect(early.ok).toBe(false);
    expect(early.message).toContain("3 week(s) old; the rule is 4");
    expect(checkStartPosition(0, 4, "Earnings call confirmed the order book.")).toEqual({ ok: true, weeks: 0, message: "override" });
  });
});
