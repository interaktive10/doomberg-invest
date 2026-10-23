import { describe, expect, it } from "vitest";
import { hashId, inMore, isCurrent, MAIN, MORE } from "@/lib/nav";

describe("the app's places (lib/nav.ts)", () => {
  it("has three main places and three under More (e2e/flow.spec.ts counts the six links)", () => {
    expect(MAIN.map((p) => p.label)).toEqual(["This week", "Candidates", "Theses"]);
    expect(MORE.map((p) => p.label)).toEqual(["Journal", "Signal Lab", "Settings"]);
    expect([...MAIN, ...MORE].map((p) => p.href)).toEqual(["/", "/candidates", "/theses", "/journal", "/lab", "/settings"]);
  });

  it("marks a place current on its own page and the pages under it, This week on the home page only", () => {
    expect(isCurrent("/", "/")).toBe(true);
    expect(isCurrent("/candidates", "/")).toBe(false);
    expect(isCurrent("/theses/0b9e", "/theses")).toBe(true);
    expect(isCurrent("/thesesx", "/theses")).toBe(false);
    expect(isCurrent("/company/1", "/candidates")).toBe(false);
  });

  it("shows More as current on Journal, Signal Lab and Settings", () => {
    expect(["/journal", "/lab", "/settings", "/settings/x"].map(inMore)).toEqual([true, true, true, true]);
    expect(["/", "/candidates", "/theses/1", "/search"].map(inMore)).toEqual([false, false, false, false]);
  });
});

describe("the element an address's hash names (PR 6 final review C13)", () => {
  it("decodes it, and gives nothing for a malformed escape instead of throwing", () => {
    expect(hashId("#fact-00000000-0000-4000-8000-0000000000f1")).toBe("fact-00000000-0000-4000-8000-0000000000f1");
    expect(hashId("#a%20b")).toBe("a b");
    expect(hashId("")).toBe("");
    expect(hashId("#fact-%E0%A4")).toBe("");
  });
});
