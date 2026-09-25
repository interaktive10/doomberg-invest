"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isAllowed, normalizeEmail } from "@/lib/allowlist";
import { env } from "@/lib/env";
import { authClient } from "@/lib/supabase/server";

/** Sends the magic link, to the allowed email only; any other address gets the same answer and no email. */
export async function sendLink(form: FormData): Promise<void> {
  const email = normalizeEmail(String(form.get("email") ?? ""));
  if (isAllowed(email, env().APP_ALLOWED_EMAIL)) {
    const h = await headers();
    const origin = h.get("origin") ?? `http://${h.get("host") ?? "127.0.0.1:3000"}`;
    const supabase = await authClient();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${origin}/auth/callback`, shouldCreateUser: true },
    });
    if (error) redirect(`/login?error=${encodeURIComponent("The sign-in link couldn't be sent. Try again.")}`);
  }
  redirect("/login?sent=1");
}
