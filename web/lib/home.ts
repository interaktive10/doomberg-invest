import { pickSection, stripSection, stripTitle } from "@/lib/cards";

// Home (overhaul PR 5; BRIEF §6): the funnel and What changed come from the digest's body_md, the same text as the
// GitHub issue. pipeline/digest/weekly.py writes "## This week" (one funnel paragraph per market), "## To do",
// "## What changed" (at most 20 "- [TICKER](APP_URL/company/<id>) <text>" lines, or "Nothing changed this week.") and
// "## Health" (the late sources, then the Actions minutes line). Home shows the first and the third: To do is read
// live from the database instead, and health is the stale banner. Pure, so tests/home.test.ts covers it.

/** A digest link to a company page ("[MTDR](https://app.example/company/<id>)", APP_URL in the issue) as a path on
 * this site, so it opens here whatever host wrote it. Other links are left as they are. */
export function localLinks(md: string): string {
  return md.replace(/\]\((?:https?:\/\/[^\s/)]+)?(\/company\/[0-9a-f-]{36})\)/gi, "]($1)");
}

/** `legacy`: a digest written before this format (no This week, no What changed: the latest row until the first
 * weekly run after overhaul PR 5) is shown as it is, less its source and quota tables (integration review web-WEB-2). */
export function homeSections(md: string): { funnel: string; changed: string; legacy: string } {
  const funnel = pickSection(md, "This week"); // in a week without scores, the sentence saying why
  const changed = localLinks(pickSection(md, "What changed"));
  const old = md.trim() !== "" && !funnel && !changed;
  const legacy = old ? localLinks(stripTitle(stripSection(stripSection(md, "Source health"), "LLM quota use")).trim()) : "";
  return { funnel, changed, legacy };
}
