import { describe, expect, it } from "vitest";
import { CAVEATS } from "@/lib/caveats";
import { repoFile } from "./repo";

describe("Signal Lab caveats (BRIEF §7: the first four, verbatim, at the top of the Lab screen)", () => {
  it("equal the brief's first four honest limits", () => {
    const brief = repoFile("docs/BRIEF.md");
    const section = brief.slice(brief.indexOf("## 7. Honest limits"));
    const lines = section.split("\n").filter((l) => /^[1-9]\. /.test(l));
    expect(CAVEATS).toEqual(lines.slice(0, 4));
  });
});
