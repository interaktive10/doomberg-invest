import { describe, expect, it } from "vitest";
import { byCategory, historyLine, isLibrary, lagWords, pct, readingWords, span, STATUS, STATUS_ORDER, STATUS_SHORT, zWords, type LibraryTheme } from "@/lib/themes";

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
