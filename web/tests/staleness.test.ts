import { describe, expect, it } from "vitest";
import type { SourceHealth } from "@/lib/data";
import { FALLBACK_OF, SLA_DAYS, onTimeCount, sourceStatus, staleSources } from "@/lib/staleness";
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

  const now = new Date("2026-09-19T03:00:00Z");
  it("names a stale source and one past its SLA", () => {
    const rows = [at("sec", "2026-09-01T06:00:00Z"), at("twelvedata", null, true), at("nse", "2026-09-12T06:00:00Z")];
    expect(staleSources(rows, now)).toEqual(["sec (no success for 17 days; SLA 8)", "twelvedata (stale)"]);
    expect(sourceStatus(rows[2] as SourceHealth, rows, now)).toBe("ok");
  });

  it("raises no alarm for a paused India's sources (docs/SPEC_ISSUES.md 46)", () => {
    expect(Object.keys(SLA_DAYS)).not.toContain("nse");
    expect(Object.keys(SLA_DAYS)).not.toContain("bse");
    expect(FALLBACK_OF).toEqual({}); // BSE stands in for NSE again when India restarts (M6 review R2-F5)
    const paused = [at("bse", "2026-08-01T06:00:00Z"), at("nse", "2026-08-01T06:00:00Z")];
    expect(staleSources(paused, now)).toEqual([]);
    expect(paused.map((s) => sourceStatus(s, paused, now))).toEqual(["ok", "ok"]);
  });

  it("reads production's never-succeeded bse row as not on time, without a banner (PR 1 review pipeline-F2)", () => {
    // BSE records a success only in a week it stood in for NSE, and production's row never has. Without its
    // fallback_of entry it reads "never succeeded" (the digest's table says the same) until Settings lists US
    // sources only (overhaul PR 4); docs/SPEC_ISSUES.md 46.
    const prod = [at("bse", null), at("nse", "2026-09-12T06:00:00Z"), at("sec", "2026-09-18T06:00:00Z")];
    expect(staleSources(prod, now)).toEqual([]);
    expect(prod.map((s) => sourceStatus(s, prod, now))).toEqual(["never succeeded", "ok", "ok"]);
    expect(onTimeCount(prod, now)).toBe(2);
  });

  it("counts the sources on time like the banner (Settings 'Sources on time')", () => {
    const fine = [at("sec", "2026-09-18T06:00:00Z"), at("nse", "2026-08-01T06:00:00Z")];
    expect(onTimeCount(fine, now)).toBe(2);
    const oneStale = [at("sec", "2026-09-18T06:00:00Z"), at("twelvedata", "2026-09-18T06:00:00Z", true)];
    expect(onTimeCount(oneStale, now)).toBe(1);
    const oneLate = [at("sec", "2026-09-01T06:00:00Z"), at("twelvedata", "2026-09-18T06:00:00Z")];
    expect(onTimeCount(oneLate, now)).toBe(1);
  });
});
