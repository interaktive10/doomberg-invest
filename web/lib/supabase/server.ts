import "server-only";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { env } from "@/lib/env";

/** The auth client (anon key + the session cookies): magic-link sign-in, the session, sign-out. */
export async function authClient() {
  const store = await cookies();
  const e = env();
  return createServerClient(e.SUPABASE_URL, e.SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return store.getAll();
      },
      setAll(list) {
        try {
          for (const { name, value, options } of list) store.set(name, value, options);
        } catch {
          // A server component can't set cookies; the middleware refreshes the session instead.
        }
      },
    },
  });
}
