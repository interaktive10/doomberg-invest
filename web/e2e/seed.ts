// The ids scripts/seed_e2e.py writes.
export const ECHO = "00000000-0000-4000-8000-0000000000e1";
export const SIGMA = "00000000-0000-4000-8000-0000000000e5";
export const LUMEN = "00000000-0000-4000-8000-0000000000e6"; // Watch, US (docs/SPEC_ISSUES.md 56)
export const TARA = "00000000-0000-4000-8000-0000000000e7"; // Watch, India
export const ECHO_THESIS = "00000000-0000-4000-8000-0000000000a1";
export const OMEGA_THESIS = "00000000-0000-4000-8000-0000000000a2"; // in Review: a kill criterion triggered
export const SIGMA_THESIS = "00000000-0000-4000-8000-0000000000a3"; // closed, with journal entries and a post-mortem
export const ALLOWED = process.env.APP_ALLOWED_EMAIL ?? "manzoor@example.com";
export const PAGES = [
  "/",
  "/candidates",
  "/candidates?bucket=early",
  "/candidates?bucket=watch",
  "/candidates?market=in",
  `/company/${ECHO}`,
  "/search?q=Corp",
  "/theses",
  `/theses/${ECHO_THESIS}`,
  `/theses/${OMEGA_THESIS}`,
  `/theses/${SIGMA_THESIS}`,
  "/journal",
  "/lab",
  "/settings",
] as const;
