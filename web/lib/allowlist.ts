// BRIEF §6 "Auth: Supabase magic link for APP_ALLOWED_EMAIL only". Pure, so the middleware, the login action and
// the auth callback share one rule (tests/allowlist.test.ts).

export function normalizeEmail(email: string | null | undefined): string {
  return (email ?? "").trim().toLowerCase();
}

export function isAllowed(email: string | null | undefined, allowed: string | null | undefined): boolean {
  const want = normalizeEmail(allowed);
  return want.length > 0 && normalizeEmail(email) === want;
}
