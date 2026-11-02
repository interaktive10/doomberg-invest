import { describe, expect, it } from "vitest";
import { nextRun, nextRunDate } from "@/lib/schedule";

describe("when the data updates next (lib/schedule.ts)", () => {
  it("finds a cron's next run after now", () => {
    const mon = new Date("2026-11-02T17:00:00Z"); // Monday
    expect(nextRun("37 22 * * 1-5", mon).toISOString()).toBe("2026-11-02T22:37:00.000Z");
    expect(nextRun("7 2 * * 6", mon).toISOString()).toBe("2026-11-07T02:07:00.000Z");
    const friLate = new Date("2026-11-06T23:00:00Z");
    expect(nextRun("37 22 * * 1-5", friLate).toISOString()).toBe("2026-11-09T22:37:00.000Z"); // over the weekend
  });

  it("names the day in IST: 22:37 UTC is the next morning there", () => {
    expect(nextRunDate("closes", new Date("2026-11-02T17:00:00Z"))).toBe("2026-11-03");
    expect(nextRunDate("weekly", new Date("2026-11-02T17:00:00Z"))).toBe("2026-11-07");
  });
});
