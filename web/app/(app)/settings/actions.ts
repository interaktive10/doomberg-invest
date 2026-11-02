"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { field, withMessage } from "@/lib/forms";
import { CHOICES, EFFORTS, TASKS, type Effort, type Task } from "@/lib/models";
import { db } from "@/lib/supabase/admin";

/** docs/SPEC_ISSUES.md 69: the OpenRouter model and reasoning effort per task (app_settings llm_models / llm_effort),
 * read by the pipeline's router on its next run. Only listed models and efforts are stored. */
export async function saveModels(form: FormData): Promise<void> {
  await requireUser();
  const models = {} as Record<Task, string>;
  const effort = {} as Record<Task, Effort>;
  for (const { key, label } of TASKS) {
    const m = field(form, `model_${key}`);
    const e = field(form, `effort_${key}`);
    if (!CHOICES.some((c) => c.id === m)) redirect(withMessage("/settings", "error", `${label}: pick a model from the list.`));
    if (!(EFFORTS as readonly string[]).includes(e)) redirect(withMessage("/settings", "error", `${label}: pick an effort from the list.`));
    models[key] = m;
    effort[key] = e as Effort;
  }
  const now = new Date().toISOString();
  const res = await db()
    .from("app_settings")
    .upsert([
      { key: "llm_models", value: models, updated_at: now },
      { key: "llm_effort", value: effort, updated_at: now },
    ]);
  if (res.error) redirect(withMessage("/settings", "error", res.error.message));
  revalidatePath("/settings");
  redirect(withMessage("/settings", "ok", "Saved. The next pipeline run uses these models."));
}
