import type { LlmUse } from "@/lib/data";
import { midSentence, pluralSource, type HealthRow } from "@/lib/home";

// Settings drawn (overhaul PR 6): each source as a dot row with a status chip, one line that says whether anything
// needs a look, and each LLM provider's week as a bar split into answered, rate-limited and failed calls. Pure, so
// tests/settings.test.ts covers it.

export type ChipTone = "good" | "warn" | "bad" | "plain";

/** lib/staleness.ts sourceStatus's text as a chip: a word, the detail it had in brackets (its SLA in days: "no success
 * for 11 days; due every 8 days"; PR 6 final review L5-14), and a tone. */
export function statusChip(text: string): { word: string; detail: string | null; tone: ChipTone } {
  const m = /^([^(]+?)\s*\((.*)\)$/.exec(text);
  const head = (m?.[1] ?? text).trim();
  const detail = m?.[2]?.replace(/; SLA (\d+)$/, "; due every $1 days") ?? null;
  if (head === "ok") return { word: "On time", detail, tone: "good" };
  if (head.startsWith("fallback")) return { word: "Not needed", detail, tone: "plain" };
  if (head === "late") return { word: "Late", detail, tone: "warn" };
  if (head === "stale") return { word: "Stale", detail, tone: "bad" };
  if (head === "never succeeded") return { word: "Never ran", detail, tone: "bad" };
  return { word: head.charAt(0).toUpperCase() + head.slice(1), detail, tone: "bad" };
}

/** Settings' line under its title: "All 3 sources are on time." or "Weekly prices need a look; the other 2 are on
 * time." A source resting as a fallback counts as fine. The names read as Home's late line says them: lower-case after
 * the first, and a Data health name ("SEC filings", "Weekly prices") is plural (PR 6 final review C8, DT-7). */
export function sourcesLine(rows: readonly Pick<HealthRow, "source" | "name" | "state">[]): string {
  if (rows.length === 0) return "No source has reported yet.";
  const bad = rows.filter((r) => r.state === "late" || r.state === "down");
  const fine = rows.length - bad.length;
  if (bad.length === 0) return rows.length === 1 ? "The one source is on time." : `All ${rows.length} sources are on time.`;
  const said = bad.map((r, i) => (i > 0 ? midSentence(r.name) : r.name));
  const names = said.length === 1 ? said[0]! : `${said.slice(0, -1).join(", ")} and ${said[said.length - 1]}`;
  const rest = fine === 0 ? "." : `; the other ${fine === 1 ? "one is" : `${fine} are`} on time.`;
  const many = bad.length > 1 || pluralSource(bad[0]!.source);
  return `${names} ${many ? "need" : "needs"} a look${rest}`;
}

/** A provider's calls split three ways: answered, rate-limited (a free tier's limit) and failed otherwise. */
export function llmParts(u: Pick<LlmUse, "calls" | "ok" | "rateLimited">): { ok: number; limited: number; failed: number } {
  const ok = Math.max(0, u.ok);
  const limited = Math.max(0, u.rateLimited);
  return { ok, limited, failed: Math.max(0, u.calls - ok - limited) };
}

/** The LLM section's line: "3 calls in 7 days; 1 hit a free-tier limit." */
export function llmLine(list: readonly Pick<LlmUse, "calls" | "rateLimited">[]): string {
  const calls = list.reduce((a, u) => a + u.calls, 0);
  const limited = list.reduce((a, u) => a + u.rateLimited, 0);
  if (calls === 0) return "No LLM calls in the last 7 days.";
  const head = `${calls.toLocaleString("en-US")} ${calls === 1 ? "call" : "calls"} in 7 days`;
  return limited === 0 ? `${head}; none hit a free-tier limit.` : `${head}; ${limited.toLocaleString("en-US")} hit a free-tier limit.`;
}

/** A token count, short: 950, 1.2K, 3.4M. */
export function tokens(n: number): string {
  if (!Number.isFinite(n)) return "0";
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(Math.round(n));
}
