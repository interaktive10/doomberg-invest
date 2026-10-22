// The company search in the nav (overhaul PR 5; BRIEF §6). The query is untrusted: it may hold letters, digits,
// spaces and . & - only, at most SEARCH_MAX characters; anything else is turned away with a plain message. What passes
// is escaped for LIKE (% and _ and the escape character itself) and sent as separate ilike filters (lib/data.ts
// searchCompanies), never spliced into a PostgREST .or() string. Pure, so tests/search.test.ts covers it.

export const SEARCH_MAX = 40;
export const SEARCH_ROWS = 20;
const ALLOWED = /^[A-Za-z0-9 .&-]+$/;

export type SearchQuery =
  | { kind: "empty" }
  | { kind: "bad"; message: string }
  | { kind: "ok"; q: string; exact: string; contains: string };

/** s with LIKE's wildcards (% and _) and its escape character (\) escaped, so they match themselves. */
export function likeEscape(s: string): string {
  return s.replace(/[\\%_]/g, (c) => `\\${c}`);
}

/** The search box's value as a query: `exact` matches a whole code (case-insensitive), `contains` a part of one or
 * of a name. Leading and trailing spaces are dropped and runs of spaces read as one. */
export function parseSearch(raw: string | undefined): SearchQuery {
  const q = (raw ?? "").trim().replace(/ {2,}/g, " ");
  if (q === "") return { kind: "empty" };
  if (q.length > SEARCH_MAX) return { kind: "bad", message: `A search can be at most ${SEARCH_MAX} characters long.` };
  if (!ALLOWED.test(q)) return { kind: "bad", message: "Search with letters, digits, spaces and . & - only." };
  const e = likeEscape(q);
  return { kind: "ok", q, exact: e, contains: `%${e}%` };
}

export interface SearchHit {
  id: string;
  market: "us" | "in";
  name: string;
  ticker: string | null;
  nse_symbol: string | null;
}

/** The one company whose code is the query (case-insensitive); null when none is, or more than one. */
export function exactMatch(hits: readonly SearchHit[], q: string): string | null {
  const u = q.toUpperCase();
  const ids = new Set(hits.filter((h) => h.ticker?.toUpperCase() === u || h.nse_symbol?.toUpperCase() === u).map((h) => h.id));
  return ids.size === 1 ? [...ids][0]! : null;
}

/** The hits once each, best first: an exact code, then a code that starts with the query, then a name that does,
 * then the rest by name; at most `limit`. */
export function rankHits(hits: readonly SearchHit[], q: string, limit = SEARCH_ROWS): SearchHit[] {
  const u = q.toUpperCase();
  const rank = (h: SearchHit) => {
    const codes = [h.ticker, h.nse_symbol].filter((c): c is string => c !== null).map((c) => c.toUpperCase());
    if (codes.includes(u)) return 0;
    if (codes.some((c) => c.startsWith(u))) return 1;
    return h.name.toUpperCase().startsWith(u) ? 2 : 3;
  };
  const once = new Map<string, SearchHit>();
  for (const h of hits) if (!once.has(h.id)) once.set(h.id, h);
  return [...once.values()].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name)).slice(0, limit);
}

/** Whether a key press lands in a place that takes text, where "/" must type a slash instead of jumping to the search
 * box. */
export function typingIn(el: { tagName?: string; isContentEditable?: boolean } | null | undefined): boolean {
  if (!el) return false;
  const tag = (el.tagName ?? "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true;
}
