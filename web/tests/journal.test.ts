import { describe, expect, it } from "vitest";
import { journalLine, recordLine, signalsNote, trackRecord } from "@/lib/journal";

describe("the Journal drawn (overhaul PR 6)", () => {
  it("counts what is there in one line", () => {
    expect(journalLine(0, 0)).toBe("Nothing written yet. What you write here stays private.");
    expect(journalLine(1, 0)).toBe("1 entry and 0 post-mortems, all private.");
    expect(journalLine(1200, 1)).toBe("1,200 entries and 1 post-mortem, all private.");
  });

  it("tallies the post-mortems: right, wrong, unclear", () => {
    const r = trackRecord([{ thesis_right: true }, { thesis_right: false }, { thesis_right: null }, { thesis_right: true }]);
    expect(r).toEqual({ right: 2, wrong: 1, unclear: 1 });
    expect(recordLine(r)).toBe("2 of 4 called right");
    expect(recordLine(trackRecord([]))).toBeNull();
  });

  it("reads the signals note of a post-mortem", () => {
    expect(signalsNote({ note: " S7 fired twice before it did. " })).toBe("S7 fired twice before it did.");
    expect(signalsNote({ note: 3 })).toBe("3");
    expect(signalsNote({})).toBe("");
    expect(signalsNote(null)).toBe("");
  });
});
