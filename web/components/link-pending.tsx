"use client";

import { useLinkStatus } from "next/link";

/** Inside a <Link>: marks it while the navigation it started waits for the server (next/link useLinkStatus):
 * app/globals.css dims and pulses the pressed tab, pill or row and runs a thin progress bar along the top of the page
 * until the next screen arrives. Screens without forms also have a loading skeleton (components/skeleton.tsx); the
 * ones with a server action that redirects back to them can't (a route Suspense boundary hangs that redirect), so
 * this is their tap's feedback. Redirects and 404s are unchanged. */
export function LinkPending() {
  const { pending } = useLinkStatus();
  return <span aria-hidden="true" className="link-pending" data-pending={pending ? "" : undefined} />;
}
