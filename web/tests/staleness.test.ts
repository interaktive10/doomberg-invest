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

  it("watches the sources the pipeline reads: sec, twelvedata, sec_13f and India's nse with bse (overhaul PR 4, 55)", () => {
    expect(Object.keys(SLA_DAYS).sort()).toEqual(["bse", "nse", "sec", "sec_13f", "twelvedata"]);
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
    expect(watched([...dead, at("sec", "2026-09-18T06:00:00Z"), at("bse", null)]).map((s) => s.source)).toEqual(["sec", "bse"]);
  });

  it("watches India again: a late NSE is named, and BSE rests while NSE is fine (docs/SPEC_ISSUES.md 55)", () => {
    expect(FALLBACK_OF).toEqual({ bse: "nse" }); // BSE stands in for NSE (M6 review R2-F5)
    const ok = [at("bse", null), at("nse", "2026-09-12T06:00:00Z"), at("sec", "2026-09-18T06:00:00Z")];
    expect(staleSources(ok, now)).toEqual([]);
    expect(watched(ok).map((s) => [s.source, sourceStatus(s, ok, now)])).toEqual([
      ["bse", "fallback, not needed (nse ok)"],
      ["nse", "ok"],
      ["sec", "ok"],
    ]);
    const late = [at("bse", null), at("nse", "2026-09-01T06:00:00Z")];
    expect(staleSources(late, now)).toEqual(["nse (no success for 17 days; SLA 10)"]); // a never-used fallback isn't late
  });
});
