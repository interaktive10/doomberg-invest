import { describe, expect, it } from "vitest";
import type { SourceHealth } from "@/lib/data";
import { FALLBACK_OF, SLA_DAYS, sourceStatus, staleSources } from "@/lib/staleness";
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

  it("doesn't flag BSE while NSE is fine, and does when NSE is down (M6 review R2-F5)", () => {
    const fine = [at("bse", "2026-08-01T06:00:00Z"), at("nse", "2026-09-18T06:00:00Z")];
    expect(staleSources(fine, now)).toEqual([]);
    expect(sourceStatus(fine[0] as SourceHealth, fine, now)).toBe("fallback, not needed (nse ok)");
    const down = [at("bse", "2026-08-01T06:00:00Z"), at("nse", null, true)];
    expect(staleSources(down, now)).toEqual(["bse (no success for 48 days; SLA 10)", "nse (stale)"]);
  });
});
