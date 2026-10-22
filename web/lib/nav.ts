// The app's places (overhaul PR 6 shell): three in the main nav (the desktop header's segmented pills and the phone's
// bottom dock), the rest under More. Pure, so tests/nav.test.ts covers it; components/nav-links.tsx draws it.

export interface Place {
  href: string;
  label: string;
  icon: "home" | "trend" | "doc" | "book" | "flask" | "gear";
}

export const MAIN: readonly Place[] = [
  { href: "/", label: "This week", icon: "home" },
  { href: "/candidates", label: "Candidates", icon: "trend" },
  { href: "/theses", label: "Theses", icon: "doc" },
];

export const MORE: readonly Place[] = [
  { href: "/journal", label: "Journal", icon: "book" },
  { href: "/lab", label: "Signal Lab", icon: "flask" },
  { href: "/settings", label: "Settings", icon: "gear" },
];

/** Whether `path` is the place at `href` or under it ("/theses/<id>" is Theses); "/" is This week only. */
export function isCurrent(path: string, href: string): boolean {
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}

/** Whether `path` is one of the places under More, so More shows as the current tab. */
export function inMore(path: string): boolean {
  return MORE.some((p) => isCurrent(path, p.href));
}
