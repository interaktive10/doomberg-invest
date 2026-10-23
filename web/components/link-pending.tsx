"use client";

import { useLinkStatus } from "next/link";

/** Inside a <Link>: marks it while the navigation it started waits for the server (next/link useLinkStatus). The
 * screens render per request and have no loading.tsx (a route Suspense boundary broke navigations after a server
 * action's redirect), so this is the tap's feedback instead: app/globals.css dims and pulses the pressed tab or pill
 * and runs a thin progress bar along the top of the page until the next screen arrives. Redirects and 404s are
 * unchanged. */
export function LinkPending() {
  const { pending } = useLinkStatus();
  return <span aria-hidden="true" className="link-pending" data-pending={pending ? "" : undefined} />;
}
