import { describe, expect, it } from "vitest";
import { measure, money } from "@/lib/format";

describe("metric values in tables (lib/format.ts measure)", () => {
  it("shows ratios to four places, scores to one and amounts shortened", () => {
    expect(measure(0.24)).toBe("0.2400");
    expect(measure("-0.05")).toBe("-0.0500");
    expect(measure(82)).toBe("82.0");
    expect(measure(1.22e9)).toBe("1.22B");
    expect(measure(null)).toBe("n/a");
    expect(measure("x")).toBe("n/a");
  });
});

describe("money as people say it (lib/format.ts money)", () => {
  it("chooses the unit after rounding, so just under a boundary reads as the next unit (PR 6 final review C6)", () => {
    expect(money(999_700, "USD")).toBe("$1M");
    expect(money(999_999_999, "USD")).toBe("$1B");
    expect(money(999_400, "USD")).toBe("$999K");
    expect(money(1_830_000, "USD")).toBe("$1.83M");
    expect(money(-80_000_000, "USD")).toBe("−$80M");
    expect(money(450, "INR")).toBe("₹450");
    expect(money(null, "USD")).toBe("n/a");
  });
});
