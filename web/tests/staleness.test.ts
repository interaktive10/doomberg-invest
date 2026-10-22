import { describe, expect, it } from "vitest";
import type { SourceHealth } from "@/lib/data";
import { FALLBACK_OF, SLA_DAYS, sourceStatus, staleSources, watched } from "@/lib/staleness";
import { repoFile, yamlBlock } from "./repo";

const at = (source: string, lastSuccess: string | null, stale = false): SourceHealth => ({
  source,
  last_success: lastSuccess,
  last_error: null,
  stale,
});

describe("staleness (BRIEF §2.7; config/staleness.yaml, as the digest reads it)", () => {
  it("uses the same SLAs and fallbacks as config/staleness.yaml", () => {
    const yaml = repoFile("config/staleness.yaml");
    const sla = Object.fromEntries(Object.entries(yamlBlock(yaml, "sla_days")).map(([k, v]) => [k, Number(v)]));
    expect(SLA_DAYS).toEqual(sla);
    expect(FALLBACK_OF).toEqual(yamlBlock(yaml, "fallback_of"));
  });

  it("watches the US sources the pipeline reads: sec, twelvedata and sec_13f (overhaul PR 4)", () => {
    expect(Object.keys(SLA_DAYS).sort()).toEqual(["sec", "sec_13f", "twelvedata"]);
  });

  const now = new Date("2026-09-19T03:00:00Z");
  it("names a stale source and one past its SLA", () => {
    const rows = [at("sec", "2026-09-01T06:00:00Z"), at("twelvedata", null, true), at("nse", "2026-09-12T06:00:00Z")];
    expect(staleSources(rows, now)).toEqual(["sec (no success for 17 days; SLA 8)", "twelvedata (stale)"]);
    expect(sourceStatus(rows[2] as SourceHealth, rows, now)).toBe("ok");
  });

  it("raises no alarm for a dead source's leftover health row, stale or old (overhaul PR 4)", () => {
    const dead = ["yahoo", "stooq", "fred", "eia", "gdelt"].map((s) => at(s, "2026-06-01T06:00:00Z", true));
    expect(staleSources([...dead, at("sec", "2026-09-18T06:00:00Z")], now)).toEqual([]);
    expect(watched([...dead, at("sec", "2026-09-18T06:00:00Z"), at("bse", null)]).map((s) => s.source)).toEqual(["sec"]);
  });

  it("raises no alarm for a paused India's sources (docs/SPEC_ISSUES.md 46)", () => {
    expect(Object.keys(SLA_DAYS)).not.toContain("nse");
    expect(Object.keys(SLA_DAYS)).not.toContain("bse");
    expect(FALLBACK_OF).toEqual({}); // BSE stands in for NSE again when India restarts (M6 review R2-F5)
    const paused = [at("bse", "2026-08-01T06:00:00Z"), at("nse", "2026-08-01T06:00:00Z")];
    expect(staleSources(paused, now)).toEqual([]);
    expect(paused.map((s) => sourceStatus(s, paused, now))).toEqual(["ok", "ok"]);
  });

  it("leaves production's never-succeeded bse row out of Settings and the banner (PR 1 review pipeline-F2)", () => {
    // BSE records a success only in a week it stood in for NSE, and production's row never has. Settings lists the
    // watched US sources only (overhaul PR 4), so it shows neither nse nor bse; docs/SPEC_ISSUES.md 46.
    const prod = [at("bse", null), at("nse", "2026-09-12T06:00:00Z"), at("sec", "2026-09-18T06:00:00Z")];
    expect(staleSources(prod, now)).toEqual([]);
    expect(watched(prod).map((s) => [s.source, sourceStatus(s, prod, now)])).toEqual([["sec", "ok"]]);
  });
});
