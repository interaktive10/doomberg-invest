import { describe, expect, it } from "vitest";
import { shiftedHeading } from "@/lib/headings";

describe("markdown headings", () => {
  it("sit under the Section's h2, so a page has one h1 (CI: the thesis page showed the card's title as a second h1)", () => {
    expect(shiftedHeading(1)).toBe("h3");
    expect(shiftedHeading(2)).toBe("h4");
    expect(shiftedHeading(4)).toBe("h6");
    expect(shiftedHeading(6)).toBe("h6");
    expect(shiftedHeading(1, 1)).toBe("h2");
  });
});
