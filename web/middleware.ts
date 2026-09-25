import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { isAllowed } from "@/lib/allowlist";
import { redirectTo } from "@/lib/redirect";

// BRIEF §6 "Auth: Supabase magic link for APP_ALLOWED_EMAIL only": every page but the sign-in flow needs a session
// whose email is the allowed one. The pages and server actions check again (lib/auth.ts requireUser).
const PUBLIC = ["/login", "/auth/callback"];

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
  const { data } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;
  if (PUBLIC.some((p) => path === p || path.startsWith(`${p}/`))) return response;
  if (!isAllowed(data.user?.email, process.env.APP_ALLOWED_EMAIL)) return redirectTo("/login");
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
