import { describe, expect, it } from "vitest";
import { packDiff, packQuarter, reviewedThrough, type FilingRow } from "@/lib/reviews";

const q = (period_end: string, filed_at: string, revenue: number): FilingRow => ({
  period_end,
  filed_at,
  revenue,
  op_income: null,
  net_income: null,
  cfo: null,
  rpo: null,
  diluted_shares: null,
});

describe("reviews (BRIEF §4.9: a review after each new quarterly filing, with the pack diff since the last one)", () => {
  const rows = [q("2026-03-31", "2026-05-01T12:00:00Z", 1.0e9), q("2026-06-30", "2026-08-05T12:00:00Z", 1.25e9)];
  const pack = { metrics: [{ id: "m:revenue:2026-03-31", period_end: "2026-03-31" }, { id: "m:c1", period_end: null }] };

  it("knows what the thesis already saw: the last review, else the card's pack, else what was filed before it", () => {
    expect(packQuarter(pack)).toBe("2026-03-31");
    expect(packQuarter({})).toBeNull();
    expect(reviewedThrough("2026-06-30", pack, rows, "2026-09-01T00:00:00Z")).toBe("2026-06-30");
    expect(reviewedThrough(null, pack, rows, "2026-09-01T00:00:00Z")).toBe("2026-03-31");
    expect(reviewedThrough(null, {}, rows, "2026-06-01T00:00:00Z")).toBe("2026-03-31");
    expect(reviewedThrough(null, {}, rows, "2026-01-01T00:00:00Z")).toBeNull();
  });

  it("makes a review only for quarters after that, with the kill criteria as they stand", () => {
    const kills = [{ metric: "m:revenue_ttm_yoy", operator: "<", threshold: 0.05, status: "ok", last_value: 0.24 }];
    const diff = packDiff(rows, "2026-03-31", kills);
    expect(diff?.quarters.map((r) => r.period_end)).toEqual(["2026-06-30"]);
    expect(diff?.kill_criteria).toEqual(kills);
    expect(packDiff(rows, "2026-06-30", kills)).toBeNull();
    expect(packDiff(rows, null, [])?.quarters).toHaveLength(2);
  });
});
