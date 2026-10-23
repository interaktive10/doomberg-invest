import { describe, expect, it } from "vitest";
import { byEntryDate, journalLine, recordLine, signalsNote, trackRecord } from "@/lib/journal";

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

  it("lists entries newest first by their date, a backdated one below a newer-dated one (PR 6 final review EYE-13)", () => {
    const e = (id: string, entry_date: string, created_at: string) => ({ id, entry_date, created_at });
    const list = [e("may", "2026-05-15", "2026-08-21T10:00:00Z"), e("aug", "2026-08-20", "2026-08-20T10:00:00Z"), e("aug-2", "2026-08-20", "2026-08-20T12:00:00Z")];
    expect(byEntryDate(list).map((x) => x.id)).toEqual(["aug-2", "aug", "may"]);
    expect(list.map((x) => x.id)).toEqual(["may", "aug", "aug-2"]); // a copy: the read's own order is untouched
  });
});
