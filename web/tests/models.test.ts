import { describe, expect, it } from "vitest";
import { CHOICES, DEFAULTS, picked, PRICE_CEILING, priceText } from "@/lib/models";

describe("the OpenRouter models Settings may pick (docs/SPEC_ISSUES.md 69)", () => {
  it("reads a listed pick and falls back to the default for anything else", () => {
    expect(picked(null, undefined)).toEqual(DEFAULTS);
    const p = picked({ extract: "z-ai/glm-5.3-flash", card: "openai/gpt-7-ultra" }, { extract: "none", card: "max" });
    expect(p.models).toEqual({ extract: "z-ai/glm-5.3-flash", card: DEFAULTS.models.card });
    expect(p.effort).toEqual({ extract: "none", card: DEFAULTS.effort.card });
  });

  it("lists nothing above the price ceiling, so a pick never raises the spend past it", () => {
    for (const c of CHOICES) expect(c.in <= PRICE_CEILING.in && c.out <= PRICE_CEILING.out).toBe(true);
    const base = CHOICES.find((c) => c.id === DEFAULTS.models.card)!;
    expect(priceText(base)).toBe("$0.045 in · $0.50 out per million tokens");
    expect(priceText(CHOICES.find((c) => c.id.endsWith("-1017"))!)).toBe("$0.30 in · $1.20 out per million tokens");
  });
});
