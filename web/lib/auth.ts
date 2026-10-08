import "server-only";
import { redirect } from "next/navigation";
import { cache } from "react";
import { isAllowed } from "@/lib/allowlist";
import { env } from "@/lib/env";
import { authClient } from "@/lib/supabase/server";

/** Every page and server action checks the session itself, besides the middleware. Cached per request, so the layout
 * and the page share one call to Supabase Auth instead of making one each. */
export const requireUser = cache(async (): Promise<{ email: string }> => {
  const supabase = await authClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email ?? null;
  if (email === null || !isAllowed(email, env().APP_ALLOWED_EMAIL)) redirect("/login");
  return { email };
});
