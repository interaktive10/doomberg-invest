import { NextResponse, type NextRequest } from "next/server";
import { isAllowed } from "@/lib/allowlist";
import { env } from "@/lib/env";
import { authClient } from "@/lib/supabase/server";

// The magic link lands here: exchange the code for a session, and keep it only for the allowed email.
export async function GET(request: NextRequest) {
  const url = request.nextUrl.clone();
  const code = url.searchParams.get("code");
  const supabase = await authClient();
  if (code) {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error && isAllowed(data.user?.email, env().APP_ALLOWED_EMAIL)) {
      url.pathname = "/";
      url.search = "";
      return NextResponse.redirect(url);
    }
    await supabase.auth.signOut();
  }
  url.pathname = "/login";
  url.search = `?error=${encodeURIComponent("That sign-in link isn't valid any more. Ask for a new one.")}`;
  return NextResponse.redirect(url);
}
