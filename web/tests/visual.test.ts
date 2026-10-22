import { describe, expect, it } from "vitest";
import { clamp, kindsLabel, meterPct, ringGeometry, sparkGeometry, splitWidths, tileText, tintFor } from "@/lib/visual";

describe("score rings (lib/visual.ts ringGeometry)", () => {
  it("draws the arc for the score out of the ring's circumference, and shows it rounded", () => {
    const g = ringGeometry(94, 22);
    expect(g.circumference).toBe(138.23);
    expect(g.length).toBe(129.94); // 94% of the ring
    expect(g.shown).toBe(94);
    expect(ringGeometry(72.5, 22).shown).toBe(73);
    expect(ringGeometry(100, 22).length).toBe(138.23);
  });

  it("keeps the arc on the ring for scores out of range, and draws none without a score", () => {
    expect(ringGeometry(140, 22)).toEqual({ circumference: 138.23, length: 138.23, shown: 100 });
    expect(ringGeometry(-5, 22)).toEqual({ circumference: 138.23, length: 0, shown: 0 });
    expect(ringGeometry(null, 22)).toEqual({ circumference: 138.23, length: 0, shown: null });
    expect(ringGeometry(Number.NaN, 22).shown).toBeNull();
  });
});

describe("bars (meterPct, splitWidths)", () => {
  it("fills a bar to value / max, within the track", () => {
    expect(meterPct(0.89, 1)).toBe(89);
    expect(meterPct(447, 1050)).toBe(42.6);
    expect(meterPct(120)).toBe(100);
    expect(meterPct(-3)).toBe(0);
    expect(meterPct(5, 0)).toBe(0);
    expect(meterPct(Number.NaN)).toBe(0);
    expect(clamp(Number.POSITIVE_INFINITY, 0, 1)).toBe(0);
  });

  it("splits a bar into its parts, scaling them down when they add up to more than the bar", () => {
    expect(splitWidths([50, 44])).toEqual([50, 44]); // Evidence 94: business 50 + insiders 44
    expect(splitWidths([80, 40])).toEqual([66.7, 33.3]);
    expect(splitWidths([30, -5, Number.NaN, 10], 80)).toEqual([37.5, 0, 0, 12.5]);
    expect(splitWidths([], 100)).toEqual([]);
  });
});

describe("sparklines (sparkGeometry)", () => {
  it("spreads the points over the width with zero always in range", () => {
    const g = sparkGeometry([1, 2, 4], 300, 80, 6);
    expect(g.zero).toBe(74); // the bottom: every value is above zero
    expect(g.runs).toEqual([{ line: "0,57 150,40 300,6", area: "0,74 0,57 150,40 300,6 300,74", dot: false }]);
  });

  it("lifts the zero line when a value falls below it, so the dip shows", () => {
    const g = sparkGeometry([98, -80, 139], 300, 80, 6);
    expect(g.zero).toBe(49.2); // 6 + 68 x 139/219
    expect(g.runs[0]!.line).toBe("0,18.7 150,74 300,6");
    // all below zero: zero is the top
    expect(sparkGeometry([-1, -2], 300, 80, 6).zero).toBe(6);
  });

  it("breaks the line at a missing value and draws a lone value as a dot", () => {
    const g = sparkGeometry([1, null, 1, 1, undefined], 400, 80, 0);
    expect(g.runs).toEqual([
      { line: "0,0 0,0", area: "0,80 0,0 0,80", dot: true },
      { line: "200,0 300,0", area: "200,80 200,0 300,0 300,80", dot: false },
    ]);
    expect(sparkGeometry([5], 300, 80, 6).runs[0]!.line).toBe("150,6 150,6");
  });

  it("has a baseline and no runs when there is nothing to draw", () => {
    expect(sparkGeometry([], 300, 80, 6)).toEqual({ zero: 74, runs: [] });
    expect(sparkGeometry([null, null], 300, 80, 6).runs).toEqual([]);
    expect(sparkGeometry([0, 0], 300, 80, 6).runs[0]!.line).toBe("0,74 300,74"); // flat at zero
  });
});

describe("ticker tiles (tintFor, tileText)", () => {
  it("gives a company the same tint every time, and spreads companies over the four", () => {
    expect(tintFor("CELH")).toBe(tintFor("celh"));
    const tints = new Set(["CELH", "EMBC", "HHH", "MTDR", "AMR", "PFE", "ECHO", "SGMA", "OMGA", "KAPPA"].map(tintFor));
    expect(tints.size).toBeGreaterThan(2);
    for (const t of tints) expect(["sky", "sage", "sand", "clay"]).toContain(t);
  });

  it("shows the code in capitals without its exchange suffix, at most five letters", () => {
    expect(tileText(" celh ")).toBe("CELH");
    expect(tileText("RELIANCE.NS")).toBe("RELIA");
    expect(tileText("TCS.BO")).toBe("TCS");
    expect(tileText("BRK.B")).toBe("BRK.B"); // a share class, not an exchange
  });
});

describe("evidence dots (kindsLabel)", () => {
  it("says how many kinds of evidence agree, and which", () => {
    expect(kindsLabel(["business", "insiders"])).toBe("2 kinds of evidence: business, insiders");
    expect(kindsLabel(["text facts"])).toBe("1 kind of evidence: text facts");
    expect(kindsLabel([])).toBe("No kind of evidence yet");
  });
});
