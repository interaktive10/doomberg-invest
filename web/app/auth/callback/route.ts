import { NextResponse, type NextRequest } from "next/server";
import { isAllowed } from "@/lib/allowlist";
import { env } from "@/lib/env";
import { authClient } from "@/lib/supabase/server";

// The magic link lands here. The email template's link carries a token hash, verified on the server (verifyOtp), so
// no code verifier has to live in the browser; a `code` (Supabase's default PKCE link) is exchanged instead. The
// session is kept only for the allowed email.
const TOKEN_TYPES = ["email", "magiclink", "signup"] as const;

export async function GET(request: NextRequest) {
  const url = request.nextUrl.clone();
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = TOKEN_TYPES.find((t) => t === url.searchParams.get("type"));
  const supabase = await authClient();
  let email: string | undefined;
  let problem: string | undefined;
  if (tokenHash && type) {
    const { data, error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    email = data.user?.email;
    problem = error?.message;
  } else if (code) {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    email = data.user?.email;
    problem = error?.message;
  } else {
    problem = "the link has no token";
  }
  if (!problem && isAllowed(email, env().APP_ALLOWED_EMAIL)) {
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }
  console.error(`auth callback: ${problem ?? "an email that isn't allowed signed in"}`);
  await supabase.auth.signOut();
  url.pathname = "/login";
  url.search = `?error=${encodeURIComponent("That sign-in link isn't valid any more. Ask for a new one.")}`;
  return NextResponse.redirect(url);
}
