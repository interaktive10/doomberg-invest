import { NextResponse, type NextRequest } from "next/server";

/** Route handlers (auth callback, sign-out): a redirect to a path on this site with a relative Location, so the
 * browser stays on the host its session cookies are set for. */
export function redirectTo(path: string, status: 303 | 307 = 307): NextResponse {
  return new NextResponse(null, { status, headers: { location: path } });
}

/** The middleware's redirect to /login. Next parses a middleware Location as an absolute URL (a relative one throws
 * "Invalid URL"), so it is built from request.nextUrl. Next reports a loopback host (127.0.0.1, [::1]) as localhost
 * there, so local runs use http://localhost:3000 (playwright.config.ts, supabase/config.toml). */
export function toLogin(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}
