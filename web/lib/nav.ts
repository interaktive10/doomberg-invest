// The app's places (the 2026-11 redesign: docs/SPEC_ISSUES.md 65): four in the main nav (the desktop header's pills and
// the phone's bottom dock), each with its own colour, the rest under More. Pure, so tests/nav.test.ts covers it;
// components/nav-links.tsx draws it.

export type PlaceTone = "accent" | "up" | "violet" | "pink" | "warn";

export interface Place {
  href: string;
  label: string;
  icon: "home" | "tag" | "trophy" | "bookmark" | "spark" | "book" | "flask" | "gear";
  tone?: PlaceTone;
  /** the phone dock's shorter label, when the full one doesn't fit six tabs */
  short?: string;
}

export const MAIN: readonly Place[] = [
  { href: "/", label: "Home", icon: "home", tone: "accent" },
  { href: "/candidates", label: "Undervalued", icon: "tag", tone: "up", short: "Value" },
  { href: "/themes", label: "Themes", icon: "spark", tone: "violet" },
  { href: "/winners", label: "Winners", icon: "trophy", tone: "pink" },
  { href: "/theses", label: "My list", icon: "bookmark", tone: "warn" },
];

export const MORE: readonly Place[] = [
  { href: "/journal", label: "Journal", icon: "book" },
  { href: "/lab", label: "Signal Lab", icon: "flask" },
  { href: "/settings", label: "Settings", icon: "gear" },
];

/** The text colour class of a place's icon (a fill-strength colour on an icon is decoration: the label carries it). */
export const TONE_TEXT: Record<PlaceTone, string> = { accent: "text-accent", up: "text-up", violet: "text-violet", pink: "text-pink", warn: "text-warn" };

/** Whether `path` is the place at `href` or under it ("/theses/<id>" is My list); "/" is Home only. */
export function isCurrent(path: string, href: string): boolean {
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}

/** Whether `path` is one of the places under More, so More shows as the current tab. */
export function inMore(path: string): boolean {
  return MORE.some((p) => isCurrent(path, p.href));
}

/** The element id an address's #hash names ("#fact-<id>"), decoded; "" for none or for a malformed escape such as a
 * cut-off "%E0%A4", which would otherwise throw and replace the page with its error screen (PR 6 final review C13). */
export function hashId(hash: string): string {
  try {
    return decodeURIComponent(hash.replace(/^#/, ""));
  } catch {
    return "";
  }
}
