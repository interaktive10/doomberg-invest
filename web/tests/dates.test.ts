import { describe, expect, it } from "vitest";
import { dayDate, isoWeek, quarterLabel, shortDate, utcDay, weekEyebrow, weekSpan } from "@/lib/dates";

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

  it("labels a chart's quarters as the Company mock does (PR 6 review design-F4)", () => {
    expect(quarterLabel("2023-09-30")).toBe("Q3 ’23");
    expect(quarterLabel("2026-06-30")).toBe("Q2 ’26");
    expect(quarterLabel("2026-01-31")).toBe("Q1 ’26"); // a fiscal quarter that ends in January
    expect(quarterLabel("2009-12-31")).toBe("Q4 ’09");
    expect(quarterLabel("n/a")).toBe("n/a");
    // a 52/53-week filer's quarter that ends in the next quarter's first week is still its own quarter, so two
    // quarters never share a label (PR 6 final review C5)
    expect(["2023-04-01", "2023-07-01", "2023-09-30", "2023-12-30", "2024-03-30"].map(quarterLabel)).toEqual(["Q1 ’23", "Q2 ’23", "Q3 ’23", "Q4 ’23", "Q1 ’24"]);
    expect(quarterLabel("2024-01-01")).toBe("Q4 ’23");
    expect(quarterLabel("2026-07-04")).toBe("Q2 ’26");
  });

  it("leaves what isn't a date as it is", () => {
    expect(utcDay("2026-02-30")).toBeNull();
    expect(shortDate("soon")).toBe("soon");
    expect(isoWeek("")).toBeNull();
    expect(weekEyebrow("n/a")).toBe("n/a");
  });
});
