import { describe, expect, it } from "vitest";
import { barScale, capFloor, capText, grewTo, signedPct, stepsOf, verdict, viewOf, type BacktestSummary, type MarketWinners } from "@/lib/winners";

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

describe("the market-cap range over the report's buckets (2026-11-02)", () => {
  const pick = (code: string, ret: number, ytd: number) => ({ company_id: code, code, name: code, sector: null, ret, start: 1, end: 2, ytd });
  const lead = (code: string, ytd: number) => ({ company_id: code, code, name: code, sector: null, ytd, start: 1, end: 2 });
  const m = {
    market: "us",
    min_cap: 1e9,
    top: [],
    leaders: [],
    this_year: { through: "2026-10-30", picks: null, average: null, stocks: 0 },
    buckets: [
      { min_cap: 1e9, max_cap: 5e9, top: [pick("A", 3, 0.1), pick("B", 1, 0.3)], leaders: [lead("A", 0.1)], ytd_sum: 1, ytd_n: 10 },
      { min_cap: 5e9, max_cap: 5e10, top: [pick("C", 2, -0.1)], leaders: [lead("C", 0.9)], ytd_sum: 2, ytd_n: 5 },
      { min_cap: 5e10, max_cap: null, top: [pick("D", 5, 0.2)], leaders: [], ytd_sum: 0.5, ytd_n: 5 },
    ],
  } as unknown as MarketWinners;

  it("says caps in each market's words", () => {
    expect([capText("us", 5e9), capText("us", 1.6e11), capText("us", 2.4e12)]).toEqual(["$5B", "$160B", "$2.4T"]);
    expect([capText("in", 5e10), capText("in", 2e12)]).toEqual(["Rs 5,000 crore", "Rs 2 lakh crore"]);
  });

  it("merges the buckets in range, best first, and the average stock from their sums", () => {
    expect(stepsOf(m)).toEqual([1e9, 5e9, 5e10]);
    const all = viewOf(m, { lo: 0, hi: 3 });
    expect(all.top.map((p) => p.code)).toEqual(["D", "A", "C", "B"]);
    expect(all.leaders.map((p) => p.code)).toEqual(["C", "A"]);
    expect(all.this_year.average).toBeCloseTo(3.5 / 20);
    expect(all.this_year.stocks).toBe(20);
    const mid = viewOf(m, { lo: 1, hi: 2 }); // $5B to $50B
    expect(mid.top.map((p) => p.code)).toEqual(["C"]);
    expect(mid.this_year.picks).toBeCloseTo(-0.1);
    expect(mid.this_year.average).toBeCloseTo(0.4);
    expect(viewOf(m, { lo: 0, hi: 1 }).top.map((p) => p.code)).toEqual(["A", "B"]); // under $5B
  });

  it("shows an older report's floor lists with no range", () => {
    const old = { ...m, buckets: undefined, top: [pick("Z", 1, 0)] } as MarketWinners;
    expect(stepsOf(old)).toEqual([]);
    expect(viewOf(old, { lo: 0, hi: 0 }).top.map((p) => p.code)).toEqual(["Z"]);
  });
});
