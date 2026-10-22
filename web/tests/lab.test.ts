import { describe, expect, it } from "vitest";
import { downloadLine, verdict, weightOf, type LabPricesRun, type LabRow } from "@/lib/lab";

const row = (signal_id: string, period: LabRow["period"], excess_mean: number | null, t_nw: number | null, horizon_m = 12): LabRow => ({
  signal_id,
  horizon_m,
  period,
  excess_mean,
  t_nw,
});

describe("the Lab verdict (BRIEF §4.10.5, pipeline/lab/proposals.py verdict)", () => {
  it("works: out of sample above zero with t_nw >= 2 and the same sign in sample", () => {
    expect(verdict("S1", [row("S1", "out_of_sample", 0.02, 2.1), row("S1", "in_sample", 0.01, 1)])).toBe("works");
    expect(verdict("L3", [row("L3", "out_of_sample", 0.02, 2), row("L3", "in_sample", 0.01, 0.4)])).toBe("works");
  });

  it("unproven: significant out of sample but not in sample, insignificant, no rows or another horizon", () => {
    expect(verdict("S1", [row("S1", "out_of_sample", 0.02, 2.1), row("S1", "in_sample", -0.01, 1)])).toBe("unproven");
    expect(verdict("S1", [row("S1", "out_of_sample", 0.02, 2.1)])).toBe("unproven");
    expect(verdict("S1", [row("S1", "out_of_sample", 0.012, 1.1), row("S1", "in_sample", 0.021, 2.4)])).toBe("unproven");
    expect(verdict("S2", [])).toBe("unproven");
    expect(verdict("S2", [row("S2", "out_of_sample", -0.03, -2.5, 24)])).toBe("unproven");
    expect(verdict("S2", [row("S2", "out_of_sample", null, null)])).toBe("unproven");
  });

  it("hurts: out of sample below zero with t_nw <= -2", () => {
    expect(verdict("S2", [row("S2", "out_of_sample", -0.03, -2)])).toBe("hurts");
    expect(verdict("S2", [row("S2", "out_of_sample", -0.03, -1.9)])).toBe("unproven");
  });

  it("S7-S12 are 'not testable yet' whatever their rows say", () => {
    for (const s of ["S7", "S8", "S9", "S10", "S12"]) {
      expect(verdict(s, [row(s, "out_of_sample", 0.05, 4), row(s, "in_sample", 0.05, 4)])).toBe("not testable yet");
    }
  });

  it("reads the weight in use from a weights_versions row", () => {
    const w = { version: "w0-equal", signals: { S1: 1.0, S2: "1.5" }, legacy: { L1: 0 } };
    expect([weightOf(w, "S1"), weightOf(w, "S2"), weightOf(w, "L1"), weightOf(w, "S3"), weightOf(null, "S1")]).toEqual([1, 1.5, 0, null, null]);
    expect(weightOf({ evidence: {} }, "S1")).toBeNull();
  });
});

describe("the price download's progress line (the lab_prices runs row)", () => {
  const run = (stats: LabPricesRun["stats"], error: string | null = null): LabPricesRun => ({ started_at: "2026-11-03T02:10:00Z", status: "partial", error, stats });

  it("says how far the download is", () => {
    expect(downloadLine(null)).toContain("not started yet");
    expect(downloadLine(run({ status: "running", tickers: 4500, ok: 1200, no_such_symbol: 30, error: 4, pending: 3266 }))).toBe(
      "Price download: 1,234 of 4,500 tickers settled (1,200 ok, 30 no such symbol, 4 error), 3,266 to go; last run 2026-11-03.",
    );
    expect(downloadLine(run({ status: "complete", tickers: 10, ok: 9, no_such_symbol: 1, error: 0, pending: 0 }))).toBe(
      "Price download: complete, 10 of 10 tickers settled (9 ok, 1 no such symbol, 0 error); last run 2026-11-03.",
    );
    expect(downloadLine(run({ status: "blocked", tickers: 0 }, "AAPL's daily series starts 2015-01-02"))).toBe(
      "Price download: blocked: AAPL's daily series starts 2015-01-02; last run 2026-11-03.",
    );
  });
});
