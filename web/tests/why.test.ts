import { describe, expect, it } from "vitest";
import { breakdown, capWords, firingSince, gapParts, inputRows, type SignalRow } from "@/lib/why";

// Overhaul PR 5: the Company page's "Why this score" (BRIEF §4.8): Evidence by family, the one-family cap in words,
// each signal's stored inputs (named when known, raw otherwise), how long it has fired, and the Gap's parts.

const sig = (signal_id: string, strength: number, fired = true): SignalRow => ({ signal_id, fired, strength, inputs: {} });

describe("why this score", () => {
  it("adds Evidence up by family: the top 2 signals of a family count, each family at most 1", () => {
    const b = breakdown([sig("S1", 0.82), sig("S3", 0.6), sig("S4", 0.3), sig("S9", 0.4), sig("S2", 0.9, false)], null, 0);
    expect(b.families.map((f) => [f.family, f.counted, f.beyond, Number(f.contribution.toFixed(2))])).toEqual([
      ["fundamentals", ["S1", "S3"], ["S4"], 1],
      ["text", ["S9"], [], 0.4],
    ]);
    expect(b.evidence).toBeCloseTo(70, 6);
    expect(b.capped).toBe(false);
    expect(capWords(b)).toBe("2 families fired (Fundamentals, Text), so the one-family cap at 55 does not apply.");
  });

  it("uses the score's weights version, and says when one family is capped at 55", () => {
    const weights = { signals: { S1: 1.5, S3: 1.0 }, families: { fundamentals: 1.0 } };
    const b = breakdown([sig("S1", 0.8), sig("S3", 0.5)], weights, 1);
    expect(b.uncapped).toBeCloseTo(50, 6); // min(1, 1.2 + 0.5) / 2
    expect(b.capped).toBe(false);
    expect(b.evidence).toBeCloseTo(40, 6);
    expect(capWords(b)).toBe("Only one family fired (Fundamentals), so Evidence is capped at 55; at 50 the cap does not bind yet. One soft red flag subtracts 10.");
    const two = breakdown([sig("S1", 1), sig("S3", 1)], { families: { fundamentals: 1.4 } }, 0);
    expect(two.capped).toBe(true);
    expect(two.evidence).toBe(55);
    expect(capWords(two)).toBe("Only one family fired (Fundamentals), so Evidence is capped at 55: it would be 70 with a second family. Evidence of 60 or more needs two.");
    expect(capWords(breakdown([], null, 2))).toBe("No signal fired, so Evidence is 0. 2 soft red flags subtract 20.");
  });

  it("names known inputs with their units and shows the rest raw", () => {
    expect(inputRows({ coverage: 0.31, gaps: [0.12, 0.15], source: "rpo", roic_8q: 0.05, mystery_key: { a: 1 }, flag: true })).toEqual([
      { key: "source", label: "Order book from", value: "rpo" },
      { key: "gaps", label: "Order-book growth minus revenue growth, last 2 quarters", value: "12.0%, 15.0%" },
      { key: "coverage", label: "Order book / TTM revenue", value: "0.31x" },
      { key: "roic_8q", label: "ROIC 8 quarters ago", value: "5.0%" },
      { key: "flag", label: "flag", value: "true" },
      { key: "mystery_key", label: "mystery_key", value: '{"a":1}' },
    ]);
    expect(inputRows({ status: "fired", sloan: 0.12, missing: ["ttm_cfo"] }, ["status"])).toEqual([
      { key: "sloan", label: "Sloan accruals", value: "12.0%" },
      { key: "missing", label: "Missing inputs", value: "ttm_cfo" },
    ]);
    expect(inputRows(null)).toEqual([]);
  });

  it("dates 'firing since' from the first week of the current unbroken run", () => {
    const weeks = ["2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25", "2026-10-02"];
    expect(firingSince("2026-10-02", weeks, ["2026-09-04", "2026-09-18", "2026-09-25", "2026-10-02"])).toBe("2026-09-18");
    expect(firingSince("2026-10-02", weeks, new Set(weeks))).toBe("2026-09-04");
    expect(firingSince("2026-10-02", weeks, ["2026-10-02"])).toBe("2026-10-02");
    expect(firingSince("2026-10-02", weeks, ["2026-09-25"])).toBeNull(); // not firing this week
    // a week the company wasn't scored doesn't break the run; later weeks are not read
    expect(firingSince("2026-09-25", ["2026-09-04", "2026-09-25", "2026-10-02"], ["2026-09-04", "2026-09-25"])).toBe("2026-09-04");
  });

  it("splits the Gap into C1-C3 with the missing parts marked", () => {
    const g = gapParts([
      { metric_id: "C1", value: 3.1, pct: 40, inputs: { score: 60, weeks: 300 } },
      { metric_id: "C2", value: null, pct: null, inputs: { missing: ["roic"] } },
      { metric_id: "C3", value: 0.2, pct: 55, inputs: { score: 45 } },
    ]);
    expect(g.parts.map((p) => [p.id, p.score, p.missing])).toEqual([["C1", 60, null], ["C2", null, "missing roic"], ["C3", 45, null]]);
    expect(g.mean).toBe(52.5);
    const one = gapParts([{ metric_id: "C1", value: 1, pct: 1, inputs: { score: 70 } }]);
    expect(one.parts.map((p) => p.missing)).toEqual([null, "not computed this week", "not computed this week"]);
    expect(one.mean).toBeNull();
  });
});
