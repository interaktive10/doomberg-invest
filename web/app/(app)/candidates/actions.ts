"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { LIVE_STATES, RESEARCH_QUEUED } from "@/lib/theses";
import { field, ISO_DATE, safePath, UUID, withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";

// BRIEF §6 Candidates and Company actions. "research" opens a research entry for the latest scored week: a thesis in
// state research (author manual, no card yet) that the weekly queue (pipeline/thesis/queue.py) packs after the
// shortlist, within its 10 packs, and the routine's card fills in place (overhaul PR 5, SPEC_ISSUES 35); meanwhile the
// company is priced and scored even outside the universe (§4.4). "dismiss" needs a reason (migration 0011's check)
// and hides the company until the evidence changes (lib/candidates.ts dismissalHolds).

export async function research(form: FormData): Promise<void> {
  await requireUser();
  const companyId = field(form, "company_id");
  const back = safePath(field(form, "back"), UUID.test(companyId) ? `/company/${companyId}` : "/candidates");
  if (!UUID.test(companyId)) redirect(withMessage(back, "error", "That company isn't valid."));
  const latest = await db().from("scores").select("week_end").order("week_end", { ascending: false }).limit(1).maybeSingle();
  if (latest.error) redirect(withMessage(back, "error", latest.error.message));
  const week = (latest.data as { week_end: string } | null)?.week_end;
  if (week === undefined) redirect(withMessage(back, "error", "No week has been scored yet, so there is nothing to research against."));
  // A second click (or a second tab) finds the entry the first made and opens it: one live thesis per company.
  const live = await db().from("theses").select("id, state, card_md").eq("company_id", companyId).in("state", [...LIVE_STATES])
    .order("created_week", { ascending: false }).limit(1).maybeSingle();
  if (live.error) redirect(withMessage(back, "error", live.error.message));
  let entry = live.data as { id: string; state: string; card_md: string } | null;
  if (entry === null) {
    const made = await db().from("theses").insert({
      company_id: companyId, state: "research", card_md: "", card_json: {}, evidence_pack: {}, author: "manual",
      validation: {}, created_week: week,
    }).select("id, state, card_md").single();
    if (made.error) redirect(withMessage(back, "error", made.error.message));
    entry = made.data as { id: string; state: string; card_md: string };
  }
  const seen = await db().from("candidate_actions").select("id").eq("company_id", companyId).eq("week_end", week)
    .eq("action", "research").limit(1);
  if (seen.error) redirect(withMessage(back, "error", seen.error.message));
  if ((seen.data ?? []).length === 0) {
    const act = await db().from("candidate_actions").insert({ company_id: companyId, week_end: week, action: "research" });
    if (act.error) redirect(withMessage(back, "error", act.error.message));
  }
  for (const path of ["/", "/candidates", "/theses", `/company/${companyId}`]) revalidatePath(path);
  const waiting = entry.state === "research" && entry.card_md.trim() === "";
  redirect(waiting ? withMessage(`/theses/${entry.id}`, "ok", RESEARCH_QUEUED) : `/theses/${entry.id}`);
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
  redirect(withMessage(back, "ok", "Dismissed until a new signal fires or Evidence moves 10."));
}
