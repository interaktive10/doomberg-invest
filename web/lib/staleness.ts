import type { SourceHealth } from "@/lib/data";

// BRIEF §2.7: "Stale beyond its SLA (US weekly 8 days; India weekly 10 days) -> a banner in the app and the digest".
// The same SLAs and fallbacks as config/staleness.yaml (pipeline.digest.weekly); tests/staleness.test.ts pins them to
// that file. A fallback source (BSE for NSE) records a success only in weeks it stood in, so it isn't late while its
// primary is fine (M6 review R2-F5). India is paused (docs/SPEC_ISSUES.md 46): its nse and bse rows and the BSE
// fallback come back with it.
export const SLA_DAYS: Record<string, number> = {
  sec: 8,
  twelvedata: 8,
  yahoo: 8,
  fred: 8,
  eia: 8,
  sec_13f: 100,
};

export const FALLBACK_OF: Record<string, string> = {};

const DAY = 86_400_000;

function ageDays(s: SourceHealth, now: Date): number | null {
  return s.last_success === null ? null : (now.getTime() - new Date(s.last_success).getTime()) / DAY;
}

export function late(s: SourceHealth, now: Date): boolean {
  const sla = SLA_DAYS[s.source];
  const age = ageDays(s, now);
  return sla !== undefined && age !== null && age > sla;
}

/** A fallback whose primary is fine: not needed, so its age says nothing. */
export function resting(s: SourceHealth, all: readonly SourceHealth[], now: Date): boolean {
  const primary = all.find((p) => p.source === FALLBACK_OF[s.source]);
  return primary !== undefined && !primary.stale && primary.last_success !== null && !late(primary, now);
}

export function sourceStatus(s: SourceHealth, all: readonly SourceHealth[], now: Date): string {
  if (resting(s, all, now)) return `fallback, not needed (${FALLBACK_OF[s.source]} ok)`;
  if (s.stale) return "stale";
  if (s.last_success === null) return "never succeeded";
  if (late(s, now)) return `late (no success for ${Math.floor(ageDays(s, now) ?? 0)} days; SLA ${SLA_DAYS[s.source]})`;
  return "ok";
}

/** Every source that is stale or past its SLA (a fallback only when its primary isn't fine), with why. */
export function lateSources(sources: readonly SourceHealth[], now: Date): { source: string; why: string }[] {
  const out: { source: string; why: string }[] = [];
  for (const s of sources) {
    if (resting(s, sources, now)) continue;
    if (s.stale) out.push({ source: s.source, why: "stale" });
    else if (late(s, now)) out.push({ source: s.source, why: `no success for ${Math.floor(ageDays(s, now) ?? 0)} days; SLA ${SLA_DAYS[s.source]}` });
  }
  return out;
}

/** How many sources are on time (Settings "Sources on time"): "ok", or a resting fallback, which lateSources and the
 * stale banner don't count as late either. */
export function onTimeCount(sources: readonly SourceHealth[], now: Date): number {
  return sources.filter((s) => resting(s, sources, now) || sourceStatus(s, sources, now) === "ok").length;
}

/** The banner's list as text, "sec (no success for 11 days; SLA 8)". */
export function staleSources(sources: readonly SourceHealth[], now: Date): string[] {
  return lateSources(sources, now).map((s) => `${s.source} (${s.why})`);
}
