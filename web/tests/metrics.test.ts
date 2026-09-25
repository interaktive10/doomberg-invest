import { describe, expect, it } from "vitest";
import { series, type QuarterRow } from "@/lib/metrics";

const row = (period_end: string, revenue: number, op_income: number): QuarterRow => ({
  period_end,
  revenue,
  op_income,
  net_income: op_income * 0.8,
  pretax_income: op_income,
  tax_expense: op_income * 0.2,
  cfo: op_income,
  capex: 10,
  da: 5,
  total_assets: 1000,
  cash: 100,
  total_debt: 200,
  equity: 500,
  rpo: 900,
  diluted_shares: 50,
  shares_outstanding: 49,
});

describe("Company page series (display only)", () => {
  it("needs four quarters for a TTM value and computes OPM, CCR and ND/EBITDA from them", () => {
    const rows = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"].map((d, i) => row(d, 100 + i * 10, 20));
    const s = series(rows, "us");
    expect(s[2]?.revenue).toBeNull();
    expect(s[3]?.revenue).toBe(460);
    expect(s[3]?.opm).toBeCloseTo(80 / 460);
    expect(s[3]?.ccr).toBeCloseTo(80 / 64);
    expect(s[3]?.nd_ebitda).toBeCloseTo(100 / 100);
    expect(s[4]?.incremental_roic).toBeNull(); // no TTM a year earlier
    expect(s[4]?.shares).toBe(50);
  });
});
