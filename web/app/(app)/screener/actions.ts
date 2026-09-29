"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { field, UUID, withMessage } from "@/lib/forms";
import { ScreenSpec, specToQuery } from "@/lib/screener";
import { db } from "@/lib/supabase/admin";

// BRIEF §6 Screener: saved screens (the spec JSON `screen(spec)` takes). Saving under an existing name replaces it.

export async function saveScreen(form: FormData): Promise<void> {
  await requireUser();
  const name = field(form, "name");
  const back = `/screener?${field(form, "query")}`;
  let spec: ScreenSpec;
  try {
    spec = ScreenSpec.parse(JSON.parse(field(form, "spec") || "{}"));
  } catch {
    redirect(withMessage(back, "error", "That screen isn't valid."));
  }
  if (name.length === 0) redirect(withMessage(back, "error", "A saved screen needs a name."));
  const res = await db().from("screens").upsert({ name, spec, updated_at: new Date().toISOString() }, { onConflict: "name" })
    .select("id").single();
  if (res.error) redirect(withMessage(back, "error", res.error.message));
  revalidatePath("/screener");
  const id = (res.data as { id: string }).id;
  redirect(withMessage(`/screener?screen=${id}&${specToQuery(spec).toString()}`, "ok", `Saved "${name}".`));
}

export async function deleteScreen(form: FormData): Promise<void> {
  await requireUser();
  const id = field(form, "screen_id");
  if (!UUID.test(id)) redirect("/screener");
  const res = await db().from("screens").delete().eq("id", id);
  if (res.error) redirect(withMessage("/screener", "error", res.error.message));
  revalidatePath("/screener");
  redirect(withMessage("/screener", "ok", "Screen deleted."));
}
