import type { SourceHealth } from "@/lib/data";

// BRIEF §2.7: "Stale beyond its SLA (US weekly 8 days; India weekly 10 days) -> a banner in the app and the digest".
// The same SLAs as config/staleness.yaml (pipeline.digest.weekly); tests/staleness.test.ts pins them to that file.
export const SLA_DAYS: Record<string, number> = {
  sec: 8,
  stooq: 8,
  gdelt: 8,
  fred: 8,
  eia: 8,
  nse: 10,
  bse: 10,
  sec_13f: 100,
};

const DAY = 86_400_000;

export function staleSources(sources: SourceHealth[], now: Date): string[] {
  const out: string[] = [];
  for (const s of sources) {
    if (s.stale) {
      out.push(`${s.source} (stale)`);
      continue;
    }
    const sla = SLA_DAYS[s.source];
    if (sla === undefined || s.last_success === null) continue;
    const age = now.getTime() - new Date(s.last_success).getTime();
    if (age > sla * DAY) out.push(`${s.source} (no success for ${Math.floor(age / DAY)} days; SLA ${sla})`);
  }
  return out;
}
