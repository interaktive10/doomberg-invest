// The ids scripts/seed_e2e.py writes.
export const ECHO = "00000000-0000-4000-8000-0000000000e1";
export const ECHO_THESIS = "00000000-0000-4000-8000-0000000000a1";
export const ALLOWED = process.env.APP_ALLOWED_EMAIL ?? "manzoor@example.com";
export const PAGES = [
  "/",
  "/candidates",
  "/candidates?bucket=early",
  `/company/${ECHO}`,
  "/theses",
  `/theses/${ECHO_THESIS}`,
  "/journal",
  "/screener?run=1&min_evidence=10",
  "/capex",
  "/lab",
  "/settings",
] as const;
