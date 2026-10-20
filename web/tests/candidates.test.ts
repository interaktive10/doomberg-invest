import { describe, expect, it } from "vitest";
import { dismissalHolds, evidenceChange, isNew, signed, windowStart, type ScorePoint } from "@/lib/candidates";

const W = "2026-09-18";
const row = (week_end: string, evidence: number, bucket = "candidate"): ScorePoint => ({ week_end, evidence, bucket });

describe("a dismissal holds until the evidence changes (overhaul PR 4)", () => {
  const then = { evidence: 62, families: ["fundamentals"], signals: ["S1"] };

  it("holds while nothing new fires and Evidence moves less than 10", () => {
    expect(dismissalHolds(then, then)).toBe(true);
    expect(dismissalHolds(then, { ...then, evidence: 71.9 })).toBe(true);
    expect(dismissalHolds(then, { ...then, evidence: 52.1 })).toBe(true);
    expect(dismissalHolds(then, { ...then, signals: [] })).toBe(true); // a signal stopping is no reason to look again
  });

  it("the name returns when Evidence moves 10 or more, either way", () => {
    expect(dismissalHolds(then, { ...then, evidence: 72 })).toBe(false);
    expect(dismissalHolds(then, { ...then, evidence: "52" })).toBe(false);
  });

  it("the name returns when a new signal or a new family fires", () => {
    expect(dismissalHolds(then, { ...then, signals: ["S1", "S3"] })).toBe(false);
    expect(dismissalHolds(then, { ...then, families: ["fundamentals", "text"], signals: ["S1", "S9"] })).toBe(false);
    expect(dismissalHolds(then, { ...then, families: ["fundamentals", "text"] })).toBe(false);
  });

  it("a dismissal without its week's scores row doesn't hide the name", () => {
    expect(dismissalHolds(null, then)).toBe(false);
  });
});

describe("the NEW badge and the Evidence change read the same 12 weeks of scores rows", () => {
  it("looks back 12 weeks", () => {
    expect(windowStart(W)).toBe("2026-06-26");
  });

  it("NEW: first week in the bucket in 12 weeks", () => {
    expect(isNew("candidate", W, [])).toBe(true);
    expect(isNew("candidate", W, [row("2026-09-11", 60, "early")])).toBe(true); // moved up from Early
    expect(isNew("candidate", W, [row("2026-09-11", 60)])).toBe(false);
    expect(isNew("candidate", W, [row("2026-06-26", 60)])).toBe(false); // 12 weeks back is inside the window
    expect(isNew("candidate", W, [row("2026-06-19", 60)])).toBe(true); // 13 weeks back is outside it
    expect(isNew("candidate", W, [row(W, 60)])).toBe(true); // this week's own row isn't history
  });

  it("the Evidence change is against the previous scored week", () => {
    const history = [row("2026-09-04", 50, "early"), row("2026-09-11", 58.4, "early")];
    expect(evidenceChange(62.5, W, history)).toBe(4.1);
    expect(evidenceChange("55", W, history)).toBe(-3.4);
    expect(evidenceChange(62.5, W, [])).toBeNull(); // first week scored
    expect(evidenceChange(62.5, W, [row("2026-06-19", 40)])).toBeNull(); // nothing within 12 weeks
    expect([signed(4.1), signed(-3.4), signed(0)]).toEqual(["+4.1", "−3.4", "0.0"]);
  });
});
