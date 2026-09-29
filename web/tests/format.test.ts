import { describe, expect, it } from "vitest";
import { measure } from "@/lib/format";

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
