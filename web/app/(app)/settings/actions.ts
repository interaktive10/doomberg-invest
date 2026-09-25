"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { field, withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";

/** BRIEF §11.9: the discipline rule's N (a thesis must be >= N weeks old before a start_position entry). */
export async function saveDiscipline(form: FormData): Promise<void> {
  await requireUser();
  const n = Number(field(form, "weeks"));
  if (!Number.isInteger(n) || n < 0 || n > 104) redirect(withMessage("/settings", "error", "Weeks is a whole number from 0 to 104."));
  const res = await db().from("app_settings").upsert({ key: "position_min_thesis_weeks", value: n, updated_at: new Date().toISOString() });
  if (res.error) redirect(withMessage("/settings", "error", res.error.message));
  revalidatePath("/settings");
  redirect(withMessage("/settings", "ok", `Saved: ${n} week(s).`));
}
