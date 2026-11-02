import { describe, expect, it } from "vitest";
import { byEntryDate } from "@/lib/journal";

describe("a thesis's journal entries", () => {
  it("lists entries newest first by their date, a backdated one below a newer-dated one (PR 6 final review EYE-13)", () => {
    const e = (id: string, entry_date: string, created_at: string) => ({ id, entry_date, created_at });
    const list = [e("may", "2026-05-15", "2026-08-21T10:00:00Z"), e("aug", "2026-08-20", "2026-08-20T10:00:00Z"), e("aug-2", "2026-08-20", "2026-08-20T12:00:00Z")];
    expect(byEntryDate(list).map((x) => x.id)).toEqual(["aug-2", "aug", "may"]);
    expect(list.map((x) => x.id)).toEqual(["may", "aug", "aug-2"]); // a copy: the read's own order is untouched
  });
});
