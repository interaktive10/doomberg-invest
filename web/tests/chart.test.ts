import { describe, expect, it } from "vitest";
import { yDomain } from "@/lib/chart";

describe("chart y-axis (lib/chart.ts)", () => {
  it("runs from zero to a little above the top, so a flat line isn't on the edge", () => {
    const [lo, hi] = yDomain([{ opm: 0.2 }, { opm: 0.2 }, { opm: null }], ["opm"]);
    expect(lo).toBe(0);
    expect(hi).toBeCloseTo(0.224);
  });

  it("goes below zero for negative values, and has a range when there is no data", () => {
    const [lo, hi] = yDomain([{ a: -0.1, b: 0.3 }], ["a", "b"]);
    expect(lo).toBeCloseTo(-0.148);
    expect(hi).toBeCloseTo(0.348);
    expect(yDomain([{ a: null }], ["a"])).toEqual([0, 1]);
    expect(yDomain([{ a: 0 }], ["a"])).toEqual([0, 0.12]);
  });
});
