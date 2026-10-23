import { describe, expect, it } from "vitest";
import {
  changeLines,
  contextValue,
  dayAfter,
  killValue,
  killReview,
  lastSnapshot,
  needsKillReview,
  packQuarter,
  packSnapshot,
  quarterReviews,
  reviewedQuarter,
  reviewedThrough,
  scoredWeek,
  stateDiff,
  type FilingRow,
  type NewItems,
  type Snapshot,
} from "@/lib/reviews";
import { nextFiling } from "@/lib/filing";

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

const NONE: NewItems = { facts: [], ownership: [], insiders: [] };
const KILLS = [{ metric: "m:revenue_ttm_yoy", operator: "<", threshold: 0.05, status: "ok", last_value: 0.24 }];
const NOW: Snapshot = {
  as_of: "2026-09-25",
  quarter: "2026-06-30",
  figures: { revenue: 1.22e9 },
  signals: ["S1", "S3"],
  red_flags: [],
  context: { C2: 0.1, evidence: 70 },
  kill: { "m:revenue_ttm_yoy": 0.2 },
};

describe("reviews (BRIEF §4.9: a review after each new quarterly filing, with the pack diff since the last one)", () => {
  const rows = [q("2026-03-31", "2026-05-01T12:00:00Z", 1.16e9), q("2026-06-30", "2026-08-05T12:00:00Z", 1.22e9)];
  const pack = {
    week_end: "2026-09-18",
    metrics: [
      { id: "m:revenue:2026-03-31", name: "revenue", period_end: "2026-03-31", value: "1160000000" },
      { id: "m:c1", period_end: null },
    ],
    signals: [
      { id: "s:S1", kind: "signal", fired: true },
      { id: "s:S9", kind: "signal", fired: true },
      { id: "s:S4", kind: "signal", fired: false },
      { id: "s:R2", kind: "red_flag", fired: true, status: "fired" },
    ],
    context: [{ id: "c:C2", value: "0.12" }, { id: "c:evidence", value: "72.5" }],
    kill_metrics: [{ id: "m:revenue_ttm_yoy", value: "0.24" }, { id: "m:evidence", value: "72.5" }],
  };

  it("knows what the thesis already saw: the last review, else the card's pack, else what was filed before it", () => {
    expect(packQuarter(pack)).toBe("2026-03-31");
    expect(packQuarter({})).toBeNull();
    expect(reviewedThrough("2026-06-30", pack, rows, "2026-09-01T00:00:00Z")).toBe("2026-06-30");
    expect(reviewedThrough(null, pack, rows, "2026-09-01T00:00:00Z")).toBe("2026-03-31");
    expect(reviewedThrough(null, {}, rows, "2026-06-01T00:00:00Z")).toBe("2026-03-31");
    expect(reviewedThrough(null, {}, rows, "2026-01-01T00:00:00Z")).toBeNull();
  });

  it("makes a review only for quarters after that, with the kill criteria as they stand", () => {
    const before = packSnapshot(pack);
    const made = quarterReviews(rows, "2026-03-31", before, NOW, KILLS, NONE);
    expect(made.map((d) => d.quarters.map((r) => r.period_end))).toEqual([["2026-06-30"]]);
    expect(made[0]?.kill_criteria).toEqual(KILLS);
    expect(made[0]?.figures.find((f) => f.name === "revenue")).toEqual({ name: "revenue", before: 1.16e9, now: 1.22e9 });
    expect(quarterReviews(rows, "2026-06-30", before, NOW, KILLS, NONE)).toEqual([]);
  });

  it("one review per new quarter (M7 review R1-F9): the state diff and the snapshot go with the latest", () => {
    const made = quarterReviews(rows, null, null, NOW, [], NONE);
    expect(made.map((d) => d.quarters[0]?.period_end)).toEqual(["2026-03-31", "2026-06-30"]);
    expect(made.map((d) => d.since)).toEqual([null, "2026-03-31"]);
    expect(made[0]?.state).toBeNull();
    expect(made[0]?.snapshot).toBeNull();
    expect(made[1]?.snapshot).toEqual(NOW);
    expect(made[1]?.figures.find((f) => f.name === "revenue")?.before).toBe(1.16e9);
  });

  it("pack diff since the last review (M7 review R1-F4): signals, red flags, context, kill metrics and new items", () => {
    const before = packSnapshot(pack);
    expect(before).toEqual({
      as_of: "2026-09-18",
      quarter: "2026-03-31",
      figures: { revenue: 1.16e9 },
      signals: ["S1", "S9"],
      red_flags: ["R2"],
      context: { C2: 0.12, evidence: 72.5 },
      kill: { "m:revenue_ttm_yoy": 0.24, "m:evidence": 72.5 },
    });
    const items: NewItems = {
      facts: [
        { id: "f1", subject: "backlog", value: 13.2e9, unit: "usd", as_of: "2026-09-20", published_at: "2026-09-21T12:00:00+00:00", quote: "q", url: null },
        { id: "f0", subject: "backlog", value: 12e9, unit: "usd", as_of: "2026-09-01", published_at: "2026-09-02T12:00:00+00:00", quote: "old", url: null },
      ],
      ownership: [{ quarter_end: "2026-06-30", filed_at: "2026-09-22T00:00:00Z" }, { filed_at: "2026-08-14T00:00:00Z" }],
      insiders: [{ person: "A", filed_at: "2026-09-19T10:00:00Z" }],
    };
    const d = stateDiff(before, NOW, items);
    expect(d.since).toBe("2026-09-18");
    expect(d.signals).toEqual({ fired: ["S3"], dropped: ["S9"] });
    expect(d.red_flags).toEqual({ fired: [], dropped: ["R2"] });
    expect(d.context).toEqual([
      { id: "C2", before: 0.12, now: 0.1 },
      { id: "evidence", before: 72.5, now: 70 },
    ]);
    expect(d.kill).toEqual([{ metric: "m:revenue_ttm_yoy", before: 0.24, now: 0.2 }]);
    expect(d.facts.map((f) => f.id)).toEqual(["f1"]);
    expect(d.ownership).toHaveLength(1);
    expect(d.insiders).toHaveLength(1);
    expect(packSnapshot({})).toBeNull();
  });

  it("red flags now come from the latest scored week (M7 review R2-F1): a scored week without a flag's row is clear", () => {
    const rows = {
      signals: [
        { week_end: "2026-09-18", signal_id: "S9", fired: true },
        { week_end: "2026-09-18", signal_id: "S4", fired: false },
        { week_end: "2026-09-11", signal_id: "S1", fired: true },
      ],
      // R1 fired in the two weeks before; the latest scored week has no R1 row (the weekly run stores no clear flag)
      flags: [
        { week_end: "2026-09-11", flag_id: "R1", inputs: { status: "fired" } },
        { week_end: "2026-09-04", flag_id: "R1", inputs: { status: "fired" } },
        { week_end: "2026-09-18", flag_id: "R3", inputs: { status: "unknown" } },
      ],
      context: [
        { week_end: "2026-09-18", metric_id: "C2", value: "0.1" },
        { week_end: "2026-09-11", metric_id: "C1", value: "3.1" },
      ],
    };
    expect(scoredWeek("2026-09-18", rows)).toEqual({ signals: ["S9"], red_flags: [], context: { C2: 0.1 } });
    expect(scoredWeek("2026-09-11", rows)).toEqual({ signals: ["S1"], red_flags: ["R1"], context: { C1: 3.1 } });
    expect(scoredWeek(null, rows)).toEqual({ signals: [], red_flags: [], context: {} });
    // so the review shows R1 as stopped since a card whose pack had it, not as started
    const card = { ...NOW, as_of: "2026-09-11", red_flags: ["R1"] };
    const d = stateDiff(card, { ...NOW, ...scoredWeek("2026-09-18", rows) }, NONE);
    expect(d.red_flags).toEqual({ fired: [], dropped: ["R1"] });
  });

  it("new facts are those published after the state compared against, whatever date they state (M7 review R2-F2)", () => {
    const before = packSnapshot(pack); // as of the card's week end, 2026-09-18
    const fact = (id: string, as_of: string, published_at: string) =>
      ({ id, subject: "backlog", value: 14e9, unit: "usd", as_of, published_at, quote: id, url: null }); // prettier-ignore
    const d = stateDiff(before, NOW, {
      ...NONE,
      facts: [
        fact("10-Q about 2026-06-30, published after the card", "2026-06-30", "2026-09-21T12:00:00+00:00"),
        fact("published on the card's week end: in its pack", "2026-06-30", "2026-09-18T20:00:00+00:00"),
        fact("published before the card", "2026-09-20", "2026-09-10T12:00:00+00:00"),
      ],
    });
    expect(d.facts.map((f) => f.id)).toEqual(["10-Q about 2026-06-30, published after the card"]);
    expect([dayAfter("2026-09-18"), dayAfter("2026-12-31"), dayAfter("2028-02-28")]).toEqual(["2026-09-19", "2027-01-01", "2028-02-29"]);
  });

  it("next review after a batch: the window after the latest reviewed quarter, in either order (M7 review R3-F1)", () => {
    // reviews for 2026-03-31 and 2026-06-30 made together; on 2026-08-10 Manzoor decides them in either order
    const q1 = (verdict: string | null) => ({ period_end: "2026-03-31", verdict });
    const q2 = (verdict: string | null) => ({ period_end: "2026-06-30", verdict });
    for (const batch of [[q1(null), q2("intact")], [q1("intact"), q2(null)], [q2("intact"), q1("intact")]]) {
      expect(nextFiling("us", "1231", reviewedQuarter(batch, null), "2026-08-10")?.closes).toBe("2026-11-14");
    }
    // the decided quarter's own window, as before: 2026-08-14, the 2026-06-30 10-Q already filed and reviewed
    expect(nextFiling("us", "1231", "2026-03-31", "2026-08-10")?.closes).toBe("2026-08-14");
    expect(reviewedQuarter([{ period_end: null }], "2026-06-30")).toBe("2026-06-30"); // only a kill-criteria review
    expect(reviewedQuarter([], null)).toBeNull();
  });

  it("compares with the snapshot stored with the last review when there is one", () => {
    const older = { ...NOW, as_of: "2026-06-01" };
    expect(lastSnapshot([
      { created_at: "2026-06-01T00:00:00Z", snapshot: older },
      { created_at: "2026-09-25T00:00:00Z", snapshot: NOW },
      { created_at: "2026-09-26T00:00:00Z", snapshot: null },
    ])).toEqual(NOW);
    expect(lastSnapshot([])).toBeNull();
  });

  it("review for a thesis in review without a new quarter (M7 review R1-F1): a kill criterion moved it there", () => {
    const decided = (verdict: string | null, created_at: string) => ({ verdict, created_at });
    expect(needsKillReview("review", [])).toBe(true);
    expect(needsKillReview("review", [decided("intact", "2026-08-10T00:00:00Z")])).toBe(true);
    expect(needsKillReview("review", [decided(null, "2026-09-20T00:00:00Z")])).toBe(false); // one is waiting
    expect(needsKillReview("review", [decided("broken", "2026-09-20T00:00:00Z")])).toBe(false); // waits for close
    expect(needsKillReview("thesis", [])).toBe(false);
    const r = killReview("2026-06-30", packSnapshot(pack), NOW, KILLS, NONE);
    expect(r.kind).toBe("kill_criteria");
    expect(r.quarters).toEqual([]);
    expect(r.kill_criteria).toEqual(KILLS);
    expect(r.state?.kill).toEqual([{ metric: "m:revenue_ttm_yoy", before: 0.24, now: 0.2 }]);
    expect(r.snapshot).toEqual(NOW);
  });
});

describe("the pack diff as the thesis page shows it (PR 6 final review V4-2, V4-9)", () => {
  it("writes a kill criterion's value in its metric's unit, as the checklist beside it does", () => {
    expect(killValue("m:revenue_ttm_yoy", 0.24)).toBe("24.0%");
    expect(killValue("m:evidence", 82)).toBe("82");
    expect(killValue("m:evidence", null)).toBe("–");
    expect(killValue("m:roic", 0.153)).toBe("15.3%");
  });

  it("writes Evidence and Gap as whole scores and the Gap's parts as stored", () => {
    expect(contextValue("evidence", 82)).toBe("82");
    expect(contextValue("gap", 61.6)).toBe("62");
    expect(contextValue("gap", null)).toBe("–");
    expect(contextValue("C2", 0.12)).toBe("0.1200");
    expect(contextValue("C1", 3.2)).toBe("3.2000");
  });

  it("lists only what changed among signals and red flags", () => {
    const none = { signals: { fired: [], dropped: [] }, red_flags: { fired: [], dropped: [] } };
    expect(changeLines(none)).toEqual([]);
    expect(changeLines({ ...none, red_flags: { fired: ["R4"], dropped: [] } })).toEqual([{ lead: "New red flags", ids: ["R4"], kind: "flag" }]);
    expect(changeLines({ signals: { fired: ["S1"], dropped: ["S7", "S9"] }, red_flags: { fired: [], dropped: ["R1"] } }).map((l) => l.lead)).toEqual([
      "New signals",
      "Signals stopped",
      "Red flags cleared",
    ]);
  });
});
