import { describe, expect, it } from "vitest";
import { dayDate, isoWeek, shortDate, utcDay, weekEyebrow, weekSpan } from "@/lib/dates";

// Overhaul PR 6: the dates Home and Candidates show. The week number is the ISO week, as the digest's title
// ("Doomberg weekly — 2026-W38", pipeline/thesis/evidence_pack.py week_label) counts it.

describe("dates as the screens say them", () => {
  it("names a day short, with its weekday, or with its year", () => {
    expect(shortDate("2026-09-18")).toBe("Sep 18");
    expect(shortDate("2026-01-02", true)).toBe("Jan 2, 2026");
    expect(dayDate("2026-10-16")).toBe("Fri, Oct 16");
    expect(shortDate("2026-09-18T06:00:00+00:00")).toBe("Sep 18"); // a timestamp's day
  });

  it("counts ISO weeks like the pipeline", () => {
    expect(isoWeek("2026-09-18")).toBe(38); // the seeded digest, "2026-W38"
    expect(isoWeek("2026-10-16")).toBe(42); // the mock's "Week 42 · Oct 12–16"
    expect(isoWeek("2027-01-01")).toBe(53); // a Friday in 2026's week 53
    expect(isoWeek("2021-01-08")).toBe(1);
    expect(isoWeek("2025-12-31")).toBe(1); // a Wednesday in 2026's week 1
  });

  it("spans the working week a Friday closes", () => {
    expect(weekSpan("2026-10-16")).toBe("Oct 12–16");
    expect(weekSpan("2026-09-04")).toBe("Aug 31 – Sep 4");
    expect(weekEyebrow("2026-10-16")).toBe("Week 42 · Oct 12–16");
    expect(weekEyebrow("2026-10-16", false)).toBe("Week 42");
  });

  it("leaves what isn't a date as it is", () => {
    expect(utcDay("2026-02-30")).toBeNull();
    expect(shortDate("soon")).toBe("soon");
    expect(isoWeek("")).toBeNull();
    expect(weekEyebrow("n/a")).toBe("n/a");
  });
});
