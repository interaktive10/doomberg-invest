import { describe, expect, it } from "vitest";
import { bandsOf, barScale, capFloor, capText, grewTo, signedPct, verdict, type BacktestSummary } from "@/lib/winners";

const S: BacktestSummary = { years: 10, first: 2016, last: 2025, growth: 4.2, average_growth: 2.1, cagr: 0.154, average_cagr: 0.077, beat: 7, best: 2020, worst: 2022 };

describe("the Winners screen's words (lib/winners.ts)", () => {
  it("signs and rounds a return, with thousands separators", () => {
    expect([0.4567, -0.031, 0, 12.4, null].map(signedPct)).toEqual(["+46%", "-3%", "0%", "+1,240%", "n/a"]);
  });

  it("says the size floor in each market's words", () => {
    expect(capFloor({ market: "us", min_cap: 1e9 })).toBe("$1B");
    expect(capFloor({ market: "in", min_cap: 5e10 })).toBe("Rs 5,000 crore");
  });

  it("calls it worked only with a real edge in most years, lost with a real deficit, else a wash", () => {
    expect(verdict(S)).toEqual({ tone: "up", title: "It worked", line: "+15% a year against +8% for the average stock; ahead in 7 of 10 years." });
    expect(verdict({ ...S, beat: 4 }).tone).toBe("flat"); // one or two huge years, behind in most: not "worked"
    expect(verdict({ ...S, cagr: 0.05 }).title).toBe("It didn't work");
    expect(verdict({ ...S, cagr: 0.08 }).title).toBe("A wash");
  });

  it("shows what $100 became and scales bars to the largest move", () => {
    expect(grewTo(4.2)).toBe("$420");
    expect(barScale([{ year: 2020, picks: [], ret: -0.5, average: 0.2, stocks: 100 }])).toBe(0.5);
    expect(barScale([])).toBe(0.01);
  });
});

describe("the market-cap slider's words and steps", () => {
  it("says caps in each market's words and falls back to one band", () => {
    expect([capText("us", 5e9), capText("us", 1.6e11), capText("us", 2.4e12)]).toEqual(["$5B", "$160B", "$2.4T"]);
    expect([capText("in", 5e10), capText("in", 2e12)]).toEqual(["Rs 5,000 crore", "Rs 2 lakh crore"]);
    const m = { market: "us", min_cap: 1e9, top: [], leaders: [], this_year: { through: null, picks: null, average: null, stocks: 0 } } as never;
    expect(bandsOf(m)).toHaveLength(1);
  });
});
