"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { latestReport } from "@/lib/data";
import { withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";
import { rethinkState, type ThemesReport } from "@/lib/themes";

/** docs/SPEC_ISSUES.md 76: "Rethink now" stores a request (app_settings themes_rethink_request); research.yml runs the
 * rethink within about 15 minutes. The web app makes no LLM call itself. At most once a day. */
export async function requestRethink(): Promise<void> {
  await requireUser();
  const report = await latestReport<ThemesReport>("themes");
  const req = await db().from("app_settings").select("value").eq("key", "themes_rethink_request").maybeSingle();
  const now = new Date();
  const state = rethinkState(report?.body.last_rethink ?? null, (req.data?.value as { at?: string } | null)?.at ?? null, now);
  if (state.kind === "done_today") redirect(withMessage("/themes", "error", "The themes were already rethought today. Next chance tomorrow."));
  if (state.kind === "pending") redirect(withMessage("/themes", "ok", "A rethink is already on its way."));
  const res = await db().from("app_settings").upsert({ key: "themes_rethink_request", value: { at: now.toISOString() }, updated_at: now.toISOString() });
  if (res.error) redirect(withMessage("/themes", "error", res.error.message));
  revalidatePath("/themes");
  redirect(withMessage("/themes", "ok", "Rethink requested: the AI rethinks the themes within about 15 minutes."));
}
