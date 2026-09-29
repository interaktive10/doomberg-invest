"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { field, ISO_DATE, withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";

/** A private note not tied to a thesis (BRIEF §6 Journal; never sent to any LLM). */
export async function addNote(form: FormData): Promise<void> {
  await requireUser();
  const date = field(form, "entry_date");
  const reason = field(form, "reason");
  if (!ISO_DATE.test(date) || reason.length === 0) redirect(withMessage("/journal", "error", "A note needs a date and some text."));
  const res = await db().from("journal").insert({ thesis_id: null, entry_date: date, action: "note", reason });
  if (res.error) redirect(withMessage("/journal", "error", res.error.message));
  revalidatePath("/journal");
  redirect(withMessage("/journal", "ok", "Note added."));
}
