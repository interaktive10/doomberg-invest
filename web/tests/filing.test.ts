import { describe, expect, it } from "vitest";
import { entryDateCheck, localToday, thesisWeeks } from "@/lib/discipline";
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
    expect(ok.ok && ok.at.toISOString()).toBe("2026-08-04T18:29:59.000Z"); // the end of 2026-08-04 in IST
    expect(entryDateCheck("2026-07-30", "2026-08-01T09:00:00Z", "2026-07-31", now).ok).toBe(false);
    expect(entryDateCheck("2026-09-26", "2026-08-01T09:00:00Z", "2026-07-31", now).ok).toBe(false);
    expect(entryDateCheck("2026-09-25", null, "2026-09-18", now).ok).toBe(true);
    expect(entryDateCheck("25/09/2026", null, "2026-09-18", now).ok).toBe(false);
  });

  it("takes today's date in IST, and never measures past now (M7 review round 2)", () => {
    const night = new Date("2026-09-25T20:00:00Z"); // 01:30 IST on 2026-09-26
    expect(localToday(night)).toBe("2026-09-26");
    expect(localToday(now)).toBe("2026-09-25"); // 15:30 IST
    const ist = entryDateCheck("2026-09-26", "2026-08-01T09:00:00Z", "2026-07-31", night);
    expect(ist.ok && ist.at.toISOString()).toBe("2026-09-25T20:00:00.000Z");
    expect(entryDateCheck("2026-09-27", "2026-08-01T09:00:00Z", "2026-07-31", night).ok).toBe(false);
    const same = entryDateCheck("2026-09-25", "2026-08-01T09:00:00Z", "2026-07-31", now);
    expect(same.ok && same.at.toISOString()).toBe("2026-09-25T10:00:00.000Z"); // not later today
  });

  it("an entry's date is an IST date: its end and the thesis's start are IST too (M7 review R3-F2)", () => {
    // accepted 01:30 IST on 2026-08-29; a start_position dated 2026-09-25 is measured at 23:59:59 IST that day
    const back = entryDateCheck("2026-09-25", "2026-08-28T20:00:00Z", "2026-08-28", new Date("2026-09-27T06:00:00Z"));
    expect(back.ok && back.at.toISOString()).toBe("2026-09-25T18:29:59.000Z");
    expect(back.ok && thesisWeeks("2026-08-28T20:00:00Z", "2026-08-28", back.at)).toBe(3); // so the 4-week rule holds
    // accepted 00:30 IST on 2026-09-26: an entry dated the IST day before is refused
    const early = entryDateCheck("2026-09-25", "2026-09-25T19:00:00Z", "2026-09-25", new Date("2026-09-26T03:00:00Z"));
    expect(early).toEqual({ ok: false, message: "A position can't start before the thesis did (2026-09-26)." });
  });

  it("the journal forms default to today's IST date", () => {
    for (const page of ["web/app/(app)/journal/page.tsx", "web/app/(app)/theses/[id]/page.tsx"]) {
      const text = repoFile(page);
      expect(text, page).toContain("localToday(new Date())");
      expect(text, page).not.toContain("toISOString().slice(0, 10)");
    }
  });
});
