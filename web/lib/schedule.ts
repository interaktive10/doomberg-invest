// When each part of the data updates next (2026-11-02: "show the current date on top ... everything should be latest").
// The crons mirror .github/workflows (tests/test_web_parity.py checks them): GitHub starts a scheduled run late, often
// by an hour, so a screen names the day, not the minute. Dates are Manzoor's (IST). Pure, so tests/schedule.test.ts
// covers it.

import { istDate } from "@/lib/discipline";

/** "minute hour * * days" crons, UTC. */
export const CRONS = {
  /** prices, fundamentals and scores (weekly.yml) */
  weekly: "7 2 * * 6",
  /** the latest closes, then Winners and Themes (closes.yml) */
  closes: "37 22 * * 1-5",
  /** new filings read into facts (daily.yml) */
  daily: "13 1 * * 2-6",
} as const;

function days(field: string): number[] {
  const out: number[] = [];
  for (const part of field.split(",")) {
    const [a, b] = part.split("-").map(Number);
    for (let d = a!; d <= (b ?? a!); d += 1) out.push(d % 7);
  }
  return out;
}

/** The next time a "m h * * days" cron fires after `now` (UTC). */
export function nextRun(cron: string, now: Date): Date {
  const [m, h, , , dow] = cron.split(" ");
  const allowed = days(dow ?? "0-6");
  for (let i = 0; i < 8; i += 1) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + i, Number(h), Number(m)));
    if (d > now && allowed.includes(d.getUTCDay())) return d;
  }
  throw new Error(`no run of ${cron} within a week`);
}

/** The IST date (YYYY-MM-DD) of a cron's next run. */
export function nextRunDate(cron: keyof typeof CRONS, now: Date): string {
  return istDate(nextRun(CRONS[cron], now));
}
