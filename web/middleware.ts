import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { isAllowed } from "@/lib/allowlist";
import { toLogin } from "@/lib/redirect";

// BRIEF §6 "Auth: Supabase magic link for APP_ALLOWED_EMAIL only": every page but the sign-in flow needs a session
// whose email is the allowed one. The pages and server actions check again (lib/auth.ts requireUser).
const PUBLIC = ["/login", "/auth/callback", "/api/keepalive"]; // keepalive: Vercel cron, returns no data

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const url = process.env.SUPABASE_URL;
  const anon = process.env.SUPABASE_ANON_KEY;
  if (!url || !anon) return new NextResponse("Server is not configured (SUPABASE_URL, SUPABASE_ANON_KEY)", { status: 500 });
  const supabase = createServerClient(url, anon, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(list: { name: string; value: string; options: CookieOptions }[]) {
        for (const { name, value } of list) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of list) response.cookies.set(name, value, options);
      },
    },
  });
  // The cookie's session (refreshed when due), not a round trip to Supabase Auth on every click: each page and server
  // action verifies the user with Auth itself (lib/auth.ts requireUser), so this only keeps strangers on /login.
  const { data } = await supabase.auth.getSession();
  const path = request.nextUrl.pathname;
  if (PUBLIC.some((p) => path === p || path.startsWith(`${p}/`))) return response;
  if (!isAllowed(data.session?.user.email, process.env.APP_ALLOWED_EMAIL)) return toLogin(request);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
