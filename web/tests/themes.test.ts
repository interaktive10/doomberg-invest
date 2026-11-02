import { describe, expect, it } from "vitest";
import { basisLines, basisShort, spanText, valueText, byCategory, historyLine, isLibrary, lagWords, pct, readingWords, span, STATUS, STATUS_ORDER, STATUS_SHORT, zWords, type LibraryTheme } from "@/lib/themes";

describe("the Themes screen's words (lib/themes.ts)", () => {
  it("says spans, readings and lags plainly", () => {
    expect([48, 12, 18, 6].map(span)).toEqual(["4 years", "1 year", "18 months", "6 months"]);
    expect(readingWords({ transform: "cohort", lag_months: 48, driver: "TOTALSA" })).toBe("the 12 months that ended 4 years ago, against the decade before");
    expect(readingWords({ transform: "yoy", lag_months: 0, driver: "filings" })).toMatch(/report rising demand/);
    expect(lagWords({ transform: "yoy", lag_months: 6 })).toBe("about 6 months later");
    expect(lagWords({ transform: "cohort", lag_months: 48 })).toBe("now");
  });

  it("reads the history check as one sentence", () => {
    expect(historyLine({ years: 14, first: 2012, last: 2025, tail_years: 5, tail_beat: 4, tail_excess: 0.061, other_excess: -0.01 })).toBe(
      "In the 5 of 14 years (2012–2025) the driver said yes, these companies beat the market 4 times, by +6% on average.",
    );
    expect(historyLine(null)).toBeNull();
    expect(pct(-0.04)).toBe("-4%");
  });

  it("tells a library report from a v1 one and groups by category", () => {
    expect(isLibrary({ version: 2, library: [] })).toBe(true);
    expect(isLibrary({ themes: [] })).toBe(false);
    const t = (slug: string, category: string) => ({ slug, category }) as LibraryTheme;
    expect(byCategory([t("a", "Housing"), t("b", "Energy"), t("c", "Housing")]).map(([c, l]) => [c, l.map((x) => x.slug)])).toEqual([
      ["Housing", ["a", "c"]],
      ["Energy", ["b"]],
    ]);
  });
});

describe("the statuses and the trigger in plain words (2026-11-02)", () => {
  it("reads a z-score as a share of the past 20 years", () => {
    expect(zWords(1.3)).toBe("higher than 90% of the past 20 years");
    expect(zWords(0)).toBe("higher than 50% of the past 20 years");
    expect(zWords(-0.5)).toBe("lower than 69% of the past 20 years");
    expect(zWords(4)).toBe("higher than 99% of the past 20 years");
    expect(zWords(null)).toBe("");
  });

  it("names every status without the jargon", () => {
    for (const s of STATUS_ORDER) {
      expect(STATUS[s].label).not.toMatch(/building|fading|priced in|watching/i);
      expect(STATUS_SHORT[s].length).toBeLessThanOrEqual(8);
    }
    expect(STATUS.building.label).toBe("Early: demand up, price not yet");
  });
});

describe("the data behind a theme (2026-11-02: \"you need to support it with data\")", () => {
  const r = { drivers: { TOTALSA: "US light vehicle sales", RSNSR: "US online and other non-store sales" }, units: { TOTALSA: "million a year", RSNSR: "million dollars" } };
  const wave = {
    driver: "TOTALSA",
    lag_months: 48,
    with_demand: 17,
    companies: 88,
    basis: {
      transform: "cohort" as const,
      now: { from: "2021-10", to: "2022-09", value: 13.902 },
      then: { from: "2011-10", to: "2021-09", value: 16.644 },
      change: -0.1647,
      peak: { year: 2016, value: 17.88 },
      through: "2026-09",
    },
  };

  it("says the wave, its size against the decade before and the highest year", () => {
    expect(basisLines(wave, r)).toEqual([
      "The wave it counts: Oct 2021–Sep 2022, when US light vehicle sales averaged 13.9 million a year: 16% below the 10 years before it (16.6 million a year).",
      "Highest year of the last 20: 2016 (17.9 million a year). Data through Sep 2026, from FRED.",
    ]);
    expect(basisShort(wave)).toBe("Oct 2021–Sep 2022: 16% below the decade before");
  });

  it("reads money, months and a filings theme plainly", () => {
    expect(valueText(124283, "million dollars")).toBe("$124 billion");
    expect(valueText(6.85, "percent")).toBe("6.85%");
    expect(spanText("2026-07", "2026-09")).toBe("Jul–Sep 2026");
    const f = { ...wave, driver: "filings", basis: { transform: "filings" as const, share: 0.193, typical: 0.12 } };
    expect(basisLines(f, r)).toEqual(["17 of 88 companies (19%) report rising demand in their filings; in the typical industry it is 12%."]);
    expect(basisLines({ ...wave, basis: undefined }, r)).toEqual([]);
  });
});


describe("Rethink now (docs/SPEC_ISSUES.md 76)", () => {
  it("is ready once a day and waits while a request is on its way", async () => {
    const { rethinkState } = await import("@/lib/themes");
    const now = new Date("2026-11-02T17:00:00Z");
    expect(rethinkState("2026-10-31", null, now)).toEqual({ kind: "ready" });
    expect(rethinkState("2026-10-31", "2026-11-02T16:55:00Z", now)).toEqual({ kind: "pending", since: "2026-11-02T16:55:00Z" });
    expect(rethinkState("2026-11-02", null, now)).toEqual({ kind: "done_today" });
  });
});
