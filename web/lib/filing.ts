// The next report after a quarter: evidence_pack.next_filing (pipeline/thesis/evidence_pack.py) ported, so a review
// verdict can move a thesis's next review date (§1.8 review dates, §4.9; M7 review R1-F3). tests/filing.test.ts pins
// both to web/tests/fixtures/next_filing.json, which tests/test_web_parity.py checks against the Python.

export interface FilingWindow {
  period_end: string;
  form: string;
  opens: string;
  closes: string;
}

const DAY = 86_400_000;

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function monthEndAfter(end: string, months: number): Date {
  const d = new Date(`${end}T00:00:00Z`);
  // the last day of the month `months` after end's month
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + months + 1, 0));
}

/** US 10-Q within 45 days of the quarter end, 10-K within 90; India results within 45 days (60 for the fiscal year's
 * last quarter). A window that closed before `today` moves on a quarter (a late filer). */
export function nextFiling(market: string, fye: string | null, latestEnd: string | null, today: string): FilingWindow | null {
  if (latestEnd === null) return null;
  const fyMonth = fye && /^\d{4}$/.test(fye) ? Number(fye.slice(0, 2)) : market === "in" ? 3 : 12;
  let end = latestEnd;
  for (let i = 0; i < 8; i++) {
    const next = monthEndAfter(end, 3);
    end = iso(next);
    const annual = next.getUTCMonth() + 1 === fyMonth;
    const days = market === "us" ? (annual ? 90 : 45) : annual ? 60 : 45;
    const form = market === "us" ? (annual ? "10-K" : "10-Q") : annual ? "annual results" : "results";
    const closes = iso(new Date(next.getTime() + days * DAY));
    if (closes >= today) return { period_end: end, form, opens: iso(new Date(next.getTime() + DAY)), closes };
  }
  return null;
}
