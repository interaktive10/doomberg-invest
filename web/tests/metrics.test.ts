import { describe, expect, it } from "vitest";
import { chartRows } from "@/lib/metrics";

describe("Company series use the §4.6 definitions (M7 review R1-F5)", () => {
  it("charts the pipeline's company_series points as they are, oldest first, with gaps for missing values", () => {
    // values as pipeline/signals/weekly.py series_points writes them (tests/signals/test_series_points.py pins them to
    // pipeline/signals/series.py: ROIC on mean invested capital, debt carried from the 10-K, S2's incremental ROIC)
    const rows = chartRows([
      { period_end: "2025-12-31", revenue_ttm: 4360, opm: 0.1497, roic: 0.1213, incremental_roic: 0.312, nd_to_ebitda: 2.4 },
      { period_end: "2025-09-30", revenue_ttm: 4200, opm: 0.14, roic: 0.1116, nd_to_ebitda: 2.61, diluted_shares: 100 },
    ]);
    expect(rows.map((r) => r.period)).toEqual(["2025-09-30", "2025-12-31"]);
    expect(rows[0]).toEqual({ period: "2025-09-30", revenue: 4200, opm: 0.14, roic: 0.1116, incremental_roic: null, ccr: null,
                              shares: 100, nd_ebitda: 2.61, rpo: null }); // prettier-ignore
    expect(rows[1]?.incremental_roic).toBe(0.312);
    expect(chartRows([])).toEqual([]);
  });
});
