// The part of pipeline/screener.py ScreenSpec (the JSON `screen(spec)` takes, db/migrations/0007) the Candidates
// screen sends: one bucket, the market and family filters and a row limit. The filter builder, saved screens and the
// CSV export went with the Screener UI (overhaul PR 4); the SQL function and pipeline/screener.py stay.
export interface ScreenSpec {
  market?: "us" | "in";
  buckets?: ("candidate" | "priced_in" | "early" | "excluded" | "none")[];
  families_all?: string[];
  limit?: number;
}
