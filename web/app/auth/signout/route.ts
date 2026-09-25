import { redirectTo } from "@/lib/redirect";
import { authClient } from "@/lib/supabase/server";

export async function POST() {
  const supabase = await authClient();
  await supabase.auth.signOut();
  return redirectTo("/login", 303);
}
