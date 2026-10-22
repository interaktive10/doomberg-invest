import { describe, expect, it } from "vitest";
import {
  columnGeometry,
  decileMeans,
  downloadLine,
  downloadProgress,
  headlines,
  isDecile,
  labHeadline,
  tally,
  verdict,
  weightOf,
  type LabPricesRun,
  type LabRow,
} from "@/lib/lab";

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

describe("the Lab screen's visuals (overhaul PR 6)", () => {
  const run = (stats: LabPricesRun["stats"], error: string | null = null): LabPricesRun => ({ started_at: "2026-11-03T02:10:00Z", status: "partial", error, stats });

  it("turns the download's row into a meter: settled of the total, how they settled, the run's day", () => {
    expect(downloadProgress(null)).toMatchObject({ state: "not started", total: 0, settled: 0, pct: 0, day: null });
    expect(downloadProgress(run({ status: "running", tickers: 4500, ok: 1200, no_such_symbol: 30, error: 4, pending: 3266 }))).toEqual({
      state: "running",
      total: 4500,
      settled: 1234,
      pending: 3266,
      ok: 1200,
      missing: 30,
      failed: 4,
      pct: 27.4,
      day: "2026-11-03",
      error: null,
    });
    expect(downloadProgress(run({ status: "complete", tickers: 10, ok: 9, no_such_symbol: 1, error: 0, pending: 0 }))).toMatchObject({ state: "complete", pct: 100 });
    // a blocked run keeps its reason; a run with no counts yet is an empty meter, not NaN
    expect(downloadProgress(run({ status: "blocked", tickers: 0 }, "AAPL's daily series starts 2015-01-02"))).toMatchObject({
      state: "blocked",
      pct: 0,
      error: "AAPL's daily series starts 2015-01-02",
    });
    expect(downloadProgress(run({}))).toMatchObject({ state: "running", total: 0, settled: 0, pct: 0 });
  });

  it("counts the verdicts and says the answer first", () => {
    const t = tally(["works", "unproven", "unproven", "not testable yet", "hurts"]);
    expect(t).toEqual({ works: 1, unproven: 2, hurts: 1, "not testable yet": 1 });
    expect(labHeadline(t, true, "complete")).toBe("1 of 4 testable signals beats the market out of sample.");
    expect(labHeadline({ ...t, works: 2 }, true, "complete")).toBe("2 of 5 testable signals beat the market out of sample.");
    expect(labHeadline({ ...t, works: 0 }, true, "complete")).toBe("Nothing beats the market yet, and 1 signal hurts.");
    expect(labHeadline({ ...t, works: 0, hurts: 0 }, true, "complete")).toBe("Nothing has proven itself yet: every testable signal is unproven.");
    expect(labHeadline(tally(["not testable yet"]), true, "complete")).toBe("Nothing the Lab can test yet.");
    expect(labHeadline(t, false, "running")).toBe("No Lab run yet: the price download comes first.");
    expect(labHeadline(t, false, "complete")).toBe("The prices are in: the first Lab run is next.");
  });

  it("gives each signal its headline: out of sample at the proposal horizon, best first, bar lengths against the largest", () => {
    const rows = [
      row("S1", "in_sample", 0.021, 2.4),
      row("S1", "out_of_sample", 0.012, 1.1),
      row("S2", "out_of_sample", -0.03, -2.5),
      row("S3", "out_of_sample", 0.05, 3, 24), // another horizon
      row("S4", "out_of_sample", null, null), // no mean
      row("S5", "out_of_sample", "0.006" as unknown as number, null),
    ];
    expect(headlines(rows)).toEqual([
      { signal: "S1", mean: 0.012, t: 1.1, share: 40 },
      { signal: "S5", mean: 0.006, t: null, share: 20 },
      { signal: "S2", mean: -0.03, t: -2.5, share: 100 },
    ]);
    expect(headlines([])).toEqual([]);
  });

  it("reads the score deciles out of sample at the proposal horizon, a gap where a decile has no row", () => {
    const rows = [row("EVIDENCE_D1", "out_of_sample", -0.01, -0.8), row("EVIDENCE_D10", "out_of_sample", 0.02, 1.3), row("GAP_D2", "out_of_sample", 0.01, 1), row("EVIDENCE_D3", "in_sample", 0.5, 9)];
    expect(rows.map((r) => isDecile(r.signal_id))).toEqual([true, true, true, true]);
    expect(["S1", "L3", "EVIDENCE", "GAP_D"].map(isDecile)).toEqual([false, false, false, false]);
    expect(decileMeans(rows, "EVIDENCE")).toEqual([-0.01, null, null, null, null, null, null, null, null, 0.02]);
    expect(decileMeans(rows, "GAP", 3)).toEqual([null, 0.01, null]);
  });

  it("draws columns either side of a zero line that moves with the signs", () => {
    // both signs: zero at 2/3 of the way down (span 0.03, 0.02 above)
    expect(columnGeometry([-0.01, null, 0.02, 0])).toEqual({
      zero: 66.7,
      bars: [
        { top: 66.7, height: 33.3, sign: -1 },
        { top: 66.7, height: 0, sign: 0 },
        { top: 0, height: 66.7, sign: 1 },
        { top: 66.7, height: 0, sign: 0 },
      ],
    });
    expect(columnGeometry([1, 2]).zero).toBe(100); // all positive: zero at the bottom
    expect(columnGeometry([-1, -2]).zero).toBe(0); // all negative: zero at the top
    expect(columnGeometry([null, null])).toEqual({ zero: 0, bars: [{ top: 0, height: 0, sign: 0 }, { top: 0, height: 0, sign: 0 }] });
  });
});
