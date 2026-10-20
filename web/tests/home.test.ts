import { describe, expect, it } from "vitest";
import { pickSection } from "@/lib/cards";
import { homeSections, localLinks } from "@/lib/home";

// Overhaul PR 5: Home shows the digest's "## This week" (the funnel) and "## What changed" sections of body_md as
// pipeline/digest/weekly.py writes them; To do comes live from the database and Health is the stale banner, so
// neither of those sections is shown. BODY is tests/digest/snapshots/digest_2026-W38.md with the minutes line of
// tests/digest/test_weekly_body.py.

const ECHO = "00000000-0000-4000-8000-0000000000e1";
const KAPPA = "00000000-0000-4000-8000-0000000000e2";
const BODY = `Week ending 2026-09-18. Research only: no orders, no price alerts.

## This week

US 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55

IN 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55

## To do

- Theses in review: 1 (Kappa Cables (KAPPA))

## What changed

- [ECHO](https://doomberg.example/company/${ECHO}) new candidate (#1): S1 fired (fundamentals, text), Evidence 72.5, Gap 58.3
- [KAPPA](https://doomberg.example/company/${KAPPA}) new candidate (#2): S1 fired (fundamentals, text), Evidence 64, Gap 58.3

## Health

**Stale data:** twelvedata (no success for 11 days; SLA 8). Signals and scores that read these sources may be out of date.

Actions: 812 of 2,000 this cycle, projected 1,340.
`;

describe("Home's cut of the digest", () => {
  it("takes the funnel paragraphs from This week and the lines of What changed, not To do or Health", () => {
    const s = homeSections(BODY);
    expect(s.funnel).toBe(
      "US 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55\n\n" +
        "IN 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55",
    );
    expect(s.changed).toBe(
      `- [ECHO](/company/${ECHO}) new candidate (#1): S1 fired (fundamentals, text), Evidence 72.5, Gap 58.3\n` +
        `- [KAPPA](/company/${KAPPA}) new candidate (#2): S1 fired (fundamentals, text), Evidence 64, Gap 58.3`,
    );
    for (const gone of ["Theses in review", "Stale data", "Actions:"]) expect(s.funnel + s.changed).not.toContain(gone);
  });

  it("ends a section at the next ## heading", () => {
    expect(pickSection(BODY, "To do")).toBe("- Theses in review: 1 (Kappa Cables (KAPPA))");
    expect(pickSection(BODY, "Health")).toContain("Actions: 812 of 2,000");
    expect(pickSection("## What changed\n- a\n### Detail\n- b\n## Health\n- c", "What changed")).toBe("- a\n### Detail\n- b");
  });

  it("shows a quiet week's and an unscored week's sentences", () => {
    const quiet = "## This week\n\nUS 4,659 → stage 456 → candidates 0 → new 0 · 440 of 456 fire one family, capped at 55\n\n" +
      "## To do\n\nNothing needs you this week.\n\n## What changed\n\nNothing changed this week.\n\n## Health\n\nSources: none late or stale.\n";
    expect(homeSections(quiet).changed).toBe("Nothing changed this week.");
    const unscored = "## This week\n\n**Candidates are missing this week:** no scores were written for 2026-09-18 (the US data " +
      "run failed, so nothing was scored; see health below).\n\n## To do\n\nNothing needs you this week.\n";
    expect(homeSections(unscored).funnel).toContain("no scores were written for 2026-09-18");
  });

  it("is empty without a digest or without the sections", () => {
    expect(homeSections("")).toEqual({ funnel: "", changed: "" });
    expect(homeSections("## Source health\n\n| a |")).toEqual({ funnel: "", changed: "" });
  });

  it("opens the digest's company links on this site, and leaves other links alone", () => {
    expect(localLinks(`[A](http://localhost:3000/company/${ECHO}) [B](/company/${ECHO}) [C](https://www.sec.gov/x)`)).toBe(
      `[A](/company/${ECHO}) [B](/company/${ECHO}) [C](https://www.sec.gov/x)`,
    );
  });
});
