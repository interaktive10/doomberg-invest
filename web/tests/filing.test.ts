import { describe, expect, it } from "vitest";
import { entryDateCheck } from "@/lib/discipline";
import { nextFiling, type FilingWindow } from "@/lib/filing";
import { repoFile } from "./repo";

interface Case {
  market: string;
  fye: string | null;
  latest_end: string | null;
  today: string;
  expected: FilingWindow | null;
}

describe("the next filing window (evidence_pack.next_filing, ported)", () => {
  it("matches the pipeline on every case of web/tests/fixtures/next_filing.json", () => {
    const cases = JSON.parse(repoFile("web/tests/fixtures/next_filing.json")) as Case[];
    expect(cases.length).toBeGreaterThan(5);
    for (const c of cases) expect(nextFiling(c.market, c.fye, c.latest_end, c.today)).toEqual(c.expected);
  });

  it("next review moves to the window after the reviewed quarter (M7 review R1-F3)", () => {
    // a US company with a December year: the 2026-09-30 review, decided 2026-11-20 -> the 10-K window closes 2027-03-31
    expect(nextFiling("us", "1231", "2026-09-30", "2026-11-20")?.closes).toBe("2027-03-31");
  });
});

describe("start_position age at the entry date (§11.9; M7 review R1-F8)", () => {
  const now = new Date("2026-09-25T10:00:00Z");
  it("measures the age at the entry's date, and refuses a date before the thesis or after today", () => {
    const ok = entryDateCheck("2026-08-04", "2026-08-01T09:00:00Z", "2026-07-31", now);
    expect(ok.ok && ok.at.toISOString()).toBe("2026-08-04T23:59:59.000Z");
    expect(entryDateCheck("2026-07-30", "2026-08-01T09:00:00Z", "2026-07-31", now).ok).toBe(false);
    expect(entryDateCheck("2026-09-26", "2026-08-01T09:00:00Z", "2026-07-31", now).ok).toBe(false);
    expect(entryDateCheck("2026-09-25", null, "2026-09-18", now).ok).toBe(true);
    expect(entryDateCheck("25/09/2026", null, "2026-09-18", now).ok).toBe(false);
  });
});
