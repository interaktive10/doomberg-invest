import { NextResponse } from "next/server";

/** A redirect to a path on this site with a relative Location. An absolute URL built from request.nextUrl can name
 * another host than the one the browser used (Next reports localhost when the browser is on 127.0.0.1), and the
 * session cookies, set for the browser's host, wouldn't follow it. */
export function redirectTo(path: string, status: 303 | 307 = 307): NextResponse {
  return new NextResponse(null, { status, headers: { location: path } });
}
