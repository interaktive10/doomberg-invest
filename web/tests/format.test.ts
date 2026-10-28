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
  it("says rupees in crore, lakh crore and lakh, with Indian grouping (docs/SPEC_ISSUES.md 56)", () => {
    expect(money(2_645_730_000_000, "INR")).toBe("₹2.65 lakh cr"); // RELIANCE's FY2025 Q4 revenue
    expect(money(264_580_000_000, "INR")).toBe("₹26,458 cr");
    expect(money(453_000_000, "INR")).toBe("₹45.3 cr");
    expect(money(5_000_000_000, "INR")).toBe("₹500 cr"); // the India market-cap floor
    expect(money(999_996_000_000, "inr")).toBe("₹1 lakh cr"); // 99,999.6 cr rounds up a unit
    expect(money(340_000, "INR")).toBe("₹3.4 lakh");
    expect(money(9_996_000, "INR")).toBe("₹1 cr");
    expect(money(12_345, "INR")).toBe("₹12,345");
    expect(money(-30_755_600_000, "INR")).toBe("−₹3,076 cr"); // KEI's FY2025 H1 operating cash flow
    expect(money(75_300_000, "INR", 3)).toBe("₹7.53 cr");
    expect(money(264_580_000_000, "INR", 3)).toBe("₹26,500 cr");
  });
});
