import { describe, expect, it } from "vitest";
import { chartValue, yScale } from "@/lib/chart";

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
    expect(chartValue(75_300_000, "money", "INR")).toBe("₹75.3M");
    expect(chartValue(-80_000_000, "money", "USD")).toBe("−$80M");
    expect(chartValue(1_210_000_000, "big")).toBe("1.2B"); // a share count: no currency
    expect(chartValue(3.94, "x")).toBe("3.9×");
    expect(chartValue(0.0531, "pct")).toBe("5.3%");
    expect(chartValue(0.05, "pct")).toBe("5.0%");
    expect(chartValue(40.4, "num")).toBe("40");
    expect(chartValue(Number.NaN, "pct")).toBe("");
  });
});
