"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { field, UUID, withMessage } from "@/lib/forms";
import { humanize } from "@/lib/labels";
import { db } from "@/lib/supabase/admin";

// BRIEF §4.11: memberships start `proposed` and count for S11 only once confirmed here (from the week they're
// decided, M5); a rejection needs a reason (migration 0009's check).
export async function decideMembership(form: FormData): Promise<void> {
  await requireUser();
  const companyId = field(form, "company_id");
  const category = field(form, "category");
  const decision = field(form, "decision");
  const reason = field(form, "reason");
  if (!UUID.test(companyId) || category.length === 0 || (decision !== "confirm" && decision !== "reject")) {
    redirect(withMessage("/capex", "error", "That membership isn't valid."));
  }
  if (decision === "reject" && reason.length === 0) redirect(withMessage("/capex", "error", "A rejection needs a reason."));
  const res = await db().from("capex_memberships").update({
    status: decision === "confirm" ? "confirmed" : "rejected",
    decided_at: new Date().toISOString(),
    decision_reason: reason || null,
  }).eq("company_id", companyId).eq("category", category).eq("status", "proposed").select("category");
  if (res.error) redirect(withMessage("/capex", "error", res.error.message));
  if ((res.data ?? []).length === 0) redirect(withMessage("/capex", "error", "That membership was already decided."));
  revalidatePath("/capex");
  const name = humanize(category);
  redirect(withMessage("/capex", "ok", decision === "confirm" ? `Confirmed: ${name}.` : `Rejected: ${name}.`));
}
