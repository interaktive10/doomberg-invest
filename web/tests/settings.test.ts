import { describe, expect, it } from "vitest";
import type { SourceHealth } from "@/lib/data";
import { healthRows } from "@/lib/home";
import { llmLine, llmParts, sourcesLine, statusChip, tokens } from "@/lib/settings";
import { sourceStatus } from "@/lib/staleness";

describe("Settings drawn (overhaul PR 6)", () => {
  it("turns each source status into a chip: a word, its detail and a tone", () => {
    expect(statusChip("ok")).toEqual({ word: "On time", detail: null, tone: "good" });
    // the SLA in days, not a bare "SLA 8" (PR 6 final review L5-14)
    expect(statusChip("late (no success for 11 days; SLA 8)")).toEqual({ word: "Late", detail: "no success for 11 days; due every 8 days", tone: "warn" });
    expect(statusChip("stale")).toEqual({ word: "Stale", detail: null, tone: "bad" });
    expect(statusChip("never succeeded")).toEqual({ word: "Never ran", detail: null, tone: "bad" });
    expect(statusChip("fallback, not needed (nse ok)")).toEqual({ word: "Not needed", detail: "nse ok", tone: "plain" });
    expect(statusChip("broken")).toEqual({ word: "Broken", detail: null, tone: "bad" });
  });

  it("reads every status lib/staleness.ts gives", () => {
    const now = new Date("2026-09-20T00:00:00Z");
    const s = (source: string, last_success: string | null, stale = false): SourceHealth => ({ source, last_success, last_error: null, stale });
    const rows = [s("sec", "2026-09-18T06:00:00Z"), s("twelvedata", null, true), s("sec_13f", "2026-03-01T00:00:00Z"), s("sec", null)];
    expect(rows.map((r) => statusChip(sourceStatus(r, rows, now)).word)).toEqual(["On time", "Stale", "Late", "Never ran"]);
  });

  it("says in one line whether a source needs a look, by its plain name", () => {
    const now = new Date("2026-09-20T00:00:00Z");
    const s = (source: string, last_success: string | null, stale = false): SourceHealth => ({ source, last_success, last_error: null, stale });
    const ok = s("sec", "2026-09-18T06:00:00Z");
    // a Data health name is plural, and lower-case after the first, as Home's late line says it (PR 6 final review C8,
    // DT-7)
    expect(sourcesLine(healthRows([ok, s("twelvedata", null, true)], now))).toBe("Weekly prices need a look; the other one is on time.");
    expect(sourcesLine(healthRows([ok, s("twelvedata", null, true), s("sec_13f", "2026-03-01T00:00:00Z")], now))).toBe(
      "Weekly prices and fund holdings (13F) need a look; the other one is on time.",
    );
    expect(sourcesLine(healthRows([s("twelvedata", null, true)], now))).toBe("Weekly prices need a look.");
    expect(sourcesLine(healthRows([s("twelvedata", null, true), s("sec", null)], now))).toBe("Weekly prices and SEC filings need a look.");
    expect(sourcesLine(healthRows([ok, s("twelvedata", "2026-09-18T06:00:00Z"), s("sec_13f", "2026-08-15T00:00:00Z")], now))).toBe(
      "All 3 sources are on time.",
    );
    expect(sourcesLine(healthRows([ok], now))).toBe("The one source is on time.");
    expect(sourcesLine([])).toBe("No source has reported yet.");
    expect(
      sourcesLine([
        { source: "bse", name: "BSE", state: "resting" },
        { source: "a", name: "A", state: "down" },
        { source: "b", name: "B", state: "ok" },
        { source: "c", name: "C", state: "ok" },
      ]),
    ).toBe("A needs a look; the other 3 are on time.");
  });

  it("splits a provider's calls into answered, rate-limited and failed", () => {
    expect(llmParts({ calls: 2, ok: 1, rateLimited: 1 })).toEqual({ ok: 1, limited: 1, failed: 0 });
    expect(llmParts({ calls: 10, ok: 6, rateLimited: 1 })).toEqual({ ok: 6, limited: 1, failed: 3 });
    expect(llmParts({ calls: 1, ok: 2, rateLimited: 0 })).toEqual({ ok: 2, limited: 0, failed: 0 }); // never negative
  });

  it("sums the week in one line", () => {
    expect(llmLine([])).toBe("No LLM calls in the last 7 days.");
    expect(llmLine([{ calls: 2, rateLimited: 1 }, { calls: 1, rateLimited: 0 }])).toBe("3 calls in 7 days; 1 hit a free-tier limit.");
    expect(llmLine([{ calls: 1, rateLimited: 0 }])).toBe("1 call in 7 days; none hit a free-tier limit.");
    expect(llmLine([{ calls: 1200, rateLimited: 0 }])).toBe("1,200 calls in 7 days; none hit a free-tier limit.");
  });

  it("writes token counts short", () => {
    expect([0, 950, 1000, 1250, 3_400_000, Number.NaN].map(tokens)).toEqual(["0", "950", "1.0K", "1.3K", "3.4M", "0"]);
  });
});
