import { describe, expect, it } from "vitest";
import { allPages } from "@/lib/paging";

/** A PostgREST stand-in: `total` rows, at most `maxRows` per response whatever range is asked for. */
function server(total: number, maxRows: number) {
  const asked: [number, number][] = [];
  const fetchPage = async (from: number, to: number) => {
    asked.push([from, to]);
    const n = Math.max(0, Math.min(to + 1, total) - from);
    return { data: Array.from({ length: Math.min(n, maxRows) }, (_, i) => from + i), error: null };
  };
  return { asked, fetchPage };
}

describe("reading a long list (M7 review R1-F12: PostgREST caps a response at max_rows)", () => {
  it("reads every row a page at a time, up to the limit", async () => {
    const s = server(1500, 1000);
    const rows = await allPages<number>(s.fetchPage, 2000);
    expect(rows.length).toBe(1500);
    expect(rows[1499]).toBe(1499);
    expect(s.asked).toEqual([[0, 999], [1000, 1999], [1500, 1999]]);
  });

  it("keeps going when the server caps a page below the page size, and stops at the limit", async () => {
    expect((await allPages<number>(server(7, 3).fetchPage, 10, 5)).length).toBe(7);
    expect((await allPages<number>(server(2500, 1000).fetchPage, 2000)).length).toBe(2000);
  });

  it("raises a PostgREST error", async () => {
    let msg = "";
    try {
      await allPages(async () => ({ data: null, error: { message: "boom" } }), 10);
    } catch (e) {
      msg = (e as Error).message;
    }
    expect(msg).toBe("boom");
  });
});
