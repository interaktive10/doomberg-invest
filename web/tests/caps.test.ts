import { describe, expect, it } from "vitest";
import { CAP_STEPS, clampRange, inCapRange, parseRange, rangeParam, rangeText } from "@/lib/caps";

describe("the market-cap range (lib/caps.ts)", () => {
  const us = CAP_STEPS.us;
  it("says a range in words", () => {
    expect(rangeText("us", us, { lo: 0, hi: us.length })).toBe("Above $1B");
    expect(rangeText("us", us, { lo: 2, hi: us.length })).toBe("Above $5B");
    expect(rangeText("us", us, { lo: 2, hi: 5 })).toBe("$5B to $50B");
    expect(rangeText("in", CAP_STEPS.in, { lo: 1, hi: 3 })).toBe("Rs 10,000 crore to Rs 50,000 crore");
  });

  it("keeps a range valid and in the address", () => {
    expect(clampRange({ lo: 5, hi: 2 }, 9)).toEqual({ lo: 5, hi: 6 });
    expect(clampRange({ lo: -1, hi: 99 }, 9)).toEqual({ lo: 0, hi: 9 });
    expect(parseRange("2-5", 9)).toEqual({ lo: 2, hi: 5 });
    expect(parseRange("junk", 9)).toEqual({ lo: 0, hi: 9 });
    expect(rangeParam({ lo: 0, hi: 9 }, 9)).toBeNull();
    expect(rangeParam({ lo: 2, hi: 5 }, 9)).toBe("2-5");
  });

  it("filters a cap: min inclusive, max exclusive, no cap only at the floor", () => {
    const r = { lo: 2, hi: 5 }; // $5B to $50B
    expect([4.9e9, 5e9, 4.99e10, 5e10].map((c) => inCapRange(c, us, r))).toEqual([false, true, true, false]);
    expect(inCapRange(null, us, r)).toBe(false);
    expect(inCapRange(null, us, { lo: 0, hi: 3 })).toBe(true);
    expect(inCapRange(9e11, us, { lo: 0, hi: us.length })).toBe(true);
  });
});
