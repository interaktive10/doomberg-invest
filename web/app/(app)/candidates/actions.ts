"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { LIVE_STATES } from "@/lib/theses";
import { field, ISO_DATE, safePath, UUID, withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";

// BRIEF §6 Candidates actions. "research" opens a thesis in state research (author manual; the weekly routine writes
// cards for the shortlist) so the company is priced and scored even outside the universe (§4.4); "dismiss" needs a
// reason (migration 0011's check) and hides the company for that week.

export async function research(form: FormData): Promise<void> {
  await requireUser();
  const back = safePath(field(form, "back"), "/candidates");
  const companyId = field(form, "company_id");
  const week = field(form, "week_end");
  if (!UUID.test(companyId) || !ISO_DATE.test(week)) redirect(withMessage(back, "error", "That candidate isn't valid."));
  const live = await db().from("theses").select("id").eq("company_id", companyId).in("state", [...LIVE_STATES])
    .order("created_week", { ascending: false }).limit(1).maybeSingle();
  if (live.error) redirect(withMessage(back, "error", live.error.message));
  let thesisId = (live.data as { id: string } | null)?.id;
  if (thesisId === undefined) {
    const made = await db().from("theses").insert({
      company_id: companyId, state: "research", card_md: "", card_json: {}, evidence_pack: {}, author: "manual",
      validation: {}, created_week: week,
    }).select("id").single();
    if (made.error) redirect(withMessage(back, "error", made.error.message));
    thesisId = (made.data as { id: string }).id;
  }
  const act = await db().from("candidate_actions").insert({ company_id: companyId, week_end: week, action: "research" });
  if (act.error) redirect(withMessage(back, "error", act.error.message));
  revalidatePath("/candidates");
  redirect(`/theses/${thesisId}`);
}

export async function dismiss(form: FormData): Promise<void> {
  await requireUser();
  const back = safePath(field(form, "back"), "/candidates");
  const companyId = field(form, "company_id");
  const week = field(form, "week_end");
  const reason = field(form, "reason");
  if (!UUID.test(companyId) || !ISO_DATE.test(week)) redirect(withMessage(back, "error", "That candidate isn't valid."));
  if (reason.length === 0) redirect(withMessage(back, "error", "A dismissal needs a reason."));
  const res = await db().from("candidate_actions").insert({ company_id: companyId, week_end: week, action: "dismiss", reason });
  if (res.error) redirect(withMessage(back, "error", res.error.message));
  revalidatePath("/candidates");
  redirect(withMessage(back, "ok", "Dismissed for this week."));
}
