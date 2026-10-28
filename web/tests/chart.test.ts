import { describe, expect, it } from "vitest";
import { chartSpan, chartValue, drawnSeries, minus, yScale } from "@/lib/chart";

describe("chart y-axis (lib/chart.ts)", () => {
  it("uses round ticks from zero to just above the top, so a flat line isn't on the chart's edge", () => {
    expect(yScale([{ opm: 0.2 }, { opm: 0.2 }, { opm: null }], ["opm"])).toEqual({ domain: [0, 0.25], ticks: [0, 0.05, 0.1, 0.15, 0.2, 0.25] });
    expect(yScale([{ revenue: 3.6e9 }, { revenue: 4.6e9 }], ["revenue"]).ticks).toEqual([0, 1e9, 2e9, 3e9, 4e9, 5e9]);
    expect(yScale([{ shares: 1.2e8 }], ["shares"]).ticks).toEqual([0, 5e7, 1e8, 1.5e8]);
    expect(yScale([{ ccr: 1.45 }], ["ccr"]).ticks).toEqual([0, 0.5, 1, 1.5, 2]);
  });

  it("goes below zero for negative values, reads every series, and has a range when there is no data", () => {
    expect(yScale([{ roic: 0.3, incremental_roic: -0.1 }], ["roic", "incremental_roic"]).ticks).toEqual([-0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4]);
    expect(yScale([{ a: null }], ["a"])).toEqual({ domain: [0, 1], ticks: [0, 0.25, 0.5, 0.75, 1] });
    expect(yScale([{ a: 0 }], ["a"])).toEqual({ domain: [0, 0.2], ticks: [0, 0.2] });
  });
});

describe("chart figures (lib/chart.ts chartValue; PR 6 review design-F4)", () => {
  it("writes money with the page's currency, multiples with ×, percentages in tenths", () => {
    expect(chartValue(818_040_000, "money", "USD")).toBe("$818M");
    expect(chartValue(1_234_000_000, "money", "USD")).toBe("$1.23B");
    expect(chartValue(75_300_000, "money", "INR")).toBe("₹7.53 cr"); // rupees in crore (docs/SPEC_ISSUES.md 56)
    expect(chartValue(-80_000_000, "money", "USD")).toBe("−$80M");
    expect(chartValue(1_210_000_000, "big")).toBe("1.2B"); // a share count: no currency
    expect(chartValue(3.94, "x")).toBe("3.9×");
    expect(chartValue(0.0531, "pct")).toBe("5.3%");
    expect(chartValue(0.05, "pct")).toBe("5.0%");
    expect(chartValue(40.4, "num")).toBe("40");
    expect(chartValue(Number.NaN, "pct")).toBe("");
  });
});

describe("what a chart card draws (lib/chart.ts; PR 6 final review V4-1, V4-6)", () => {
  const q = (period: string, revenue: number | null, roic: number | null = null) => ({ period, revenue, roic });

  it("spans the periods its own series has: leading and trailing empty quarters dropped, a gap inside kept", () => {
    const data = [q("2024-09-30", null), q("2024-12-31", null), q("2025-03-31", 1), q("2025-06-30", null), q("2025-09-30", 3), q("2025-12-31", null)];
    expect(chartSpan(data, ["revenue"]).map((r) => r.period)).toEqual(["2025-03-31", "2025-06-30", "2025-09-30"]);
    expect(chartSpan(data, ["roic"])).toEqual([]);
    expect(chartSpan([q("a", 1), q("b", 2)], ["revenue"])).toHaveLength(2);
    // any of the card's series opens the span
    expect(chartSpan([q("a", null, 0.1), q("b", 2), q("c", null)], ["revenue", "roic"]).map((r) => r.period)).toEqual(["a", "b"]);
  });

  it("draws and keys only the series that have a value, each keeping its place for its colour and dash", () => {
    const series = [
      { key: "roic", label: "ROIC" },
      { key: "incremental_roic", label: "On new capital" },
    ];
    expect(drawnSeries([{ roic: 0.13, incremental_roic: null }], series)).toEqual([{ key: "roic", label: "ROIC", i: 0 }]);
    expect(drawnSeries([{ roic: null, incremental_roic: 0.2 }], series)).toEqual([{ key: "incremental_roic", label: "On new capital", i: 1 }]);
    expect(drawnSeries([{ roic: 0.1 }, { incremental_roic: 0.2 }], series).map((s) => s.i)).toEqual([0, 1]);
  });
});

describe("chart figures at the edges (PR 6 final review C6, C12)", () => {
  it("takes the next unit when a value rounds to 1000 of one", () => {
    expect(chartValue(999_600_000, "money", "USD")).toBe("$1B");
    expect(chartValue(999_960, "big")).toBe("1.0M");
    expect(chartValue(999_940, "big")).toBe("999.9K");
    expect(chartValue(999.96, "big")).toBe("1.0K");
  });

  it("writes a negative with a true minus, and no minus on a value that rounds to zero", () => {
    expect(chartValue(-0.4, "x")).toBe("−0.4×");
    expect(chartValue(-1.2e6, "big")).toBe("−1.2M");
    expect(chartValue(-0.0004, "pct")).toBe("0.0%");
    expect(chartValue(-0.4, "num")).toBe("0");
    expect(minus("-3")).toBe("−3");
    expect(minus("3")).toBe("3");
  });
});
