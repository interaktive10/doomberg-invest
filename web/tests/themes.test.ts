import { describe, expect, it } from "vitest";
import { evidenceLine, reviewOf, sharePct } from "@/lib/themes";

describe("the Themes screen's words (lib/themes.ts)", () => {
  it("says a fact's kind in plain words", () => {
    expect(evidenceLine("order_win: a $40M transformer order")).toBe("Order win: a $40M transformer order");
    expect(evidenceLine("revenue growth accelerating")).toBe("Revenue growth accelerating");
  });

  it("finds this week's review of an earlier call and clamps a share to a bar width", () => {
    const r = [{ market: "us", industry: "Grid", decision: "keep" as const, reason: "orders keep coming" }];
    expect(reviewOf(r, { market: "us", industry: "Grid" })?.decision).toBe("keep");
    expect(reviewOf(r, { market: "in", industry: "Grid" })).toBeUndefined();
    expect([0.666, 1.2, -1].map(sharePct)).toEqual([67, 100, 0]);
  });
});
