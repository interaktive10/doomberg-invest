"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { journal as journalOf, setting, thesis as getThesis, type JournalEntry } from "@/lib/data";
import { checkStartPosition, thesisWeeks } from "@/lib/discipline";
import { field, ISO_DATE, UUID, withMessage } from "@/lib/forms";
import { db } from "@/lib/supabase/admin";
import { afterVerdict, canMove, positionOpen } from "@/lib/theses";

// BRIEF §1.8 and §4.9: the thesis workflow's writes. Every action checks the session, the id and the state, then
// returns to the thesis page with ?ok= or ?error=. Journal entries and post-mortems stay in the database (never sent
// to any LLM: the web app makes no LLM calls, M7-02).

const ACTIONS = ["note", "start_position", "add", "trim", "exit", "review"] as const;
type JournalAction = (typeof ACTIONS)[number];
const VERDICTS = ["intact", "weakened", "broken"] as const;

function page(id: string): string {
  return `/theses/${id}`;
}

function done(id: string, message: string): never {
  revalidatePath(page(id));
  revalidatePath("/theses");
  redirect(withMessage(page(id), "ok", message));
}

function fail(id: string, message: string): never {
  redirect(withMessage(page(id), "error", message));
}

async function load(form: FormData) {
  await requireUser();
  const id = field(form, "thesis_id");
  if (!UUID.test(id)) redirect("/theses");
  const t = await getThesis(id);
  if (t === null) redirect("/theses");
  return t;
}

async function setState(id: string, patch: Record<string, unknown>): Promise<string | null> {
  const res = await db().from("theses").update({ ...patch, updated_at: new Date().toISOString() }).eq("id", id);
  return res.error ? res.error.message : null;
}

export async function accept(form: FormData): Promise<void> {
  const t = await load(form);
  if (!canMove(t.state, "accept")) fail(t.id, "Only a card in research can be accepted.");
  const nf = t.evidence_pack.next_filing;
  const next = typeof nf === "object" && nf !== null ? (nf as Record<string, unknown>).closes : undefined;
  const err = await setState(t.id, {
    state: "thesis",
    accepted_at: new Date().toISOString(),
    ...(typeof next === "string" && ISO_DATE.test(next) ? { next_review: next } : {}),
  });
  if (err) fail(t.id, err);
  done(t.id, "Accepted: this is now a thesis with monitoring and kill criteria.");
}

export async function dismissThesis(form: FormData): Promise<void> {
  const t = await load(form);
  const reason = field(form, "reason");
  if (!canMove(t.state, "dismiss")) fail(t.id, "Only a card in research can be dismissed.");
  if (reason.length === 0) fail(t.id, "A dismissal needs a reason.");
  const err = await setState(t.id, { state: "dismissed", dismissed_reason: reason });
  if (err) fail(t.id, err);
  done(t.id, "Dismissed.");
}

export async function addJournal(form: FormData): Promise<void> {
  const t = await load(form);
  const action = ACTIONS.find((a) => a === field(form, "action")) as JournalAction | undefined;
  const date = field(form, "entry_date");
  const reason = field(form, "reason");
  const pctText = field(form, "portfolio_pct");
  const override = field(form, "override_reason");
  if (action === undefined) fail(t.id, "Pick an action.");
  if (!ISO_DATE.test(date)) fail(t.id, "The entry needs a date.");
  if (reason.length === 0) fail(t.id, "The entry needs a reason.");
  const pct = pctText === "" ? null : Number(pctText);
  if (pct !== null && !(Number.isFinite(pct) && pct > 0 && pct <= 100)) fail(t.id, "% of portfolio is a number above 0 and at most 100.");
  const entries: JournalEntry[] = await journalOf(t.id);
  const open = positionOpen(entries);
  let overrideReason: string | null = null;
  if (action === "start_position") {
    if (t.state !== "thesis" && t.state !== "position" && t.state !== "review") fail(t.id, "Accept the card as a thesis before starting a position.");
    if (open) fail(t.id, "A position is already open.");
    const minWeeks = Number(await setting<number | string>("position_min_thesis_weeks", 4));
    const check = checkStartPosition(thesisWeeks(t.accepted_at, t.created_week, new Date()), minWeeks, override);
    if (!check.ok) fail(t.id, check.message);
    overrideReason = check.message === "override" ? override : null;
  } else if ((action === "add" || action === "trim" || action === "exit") && !open) {
    fail(t.id, "There is no open position.");
  }
  const res = await db().from("journal").insert({
    thesis_id: t.id, entry_date: date, action, portfolio_pct: pct, reason, override_reason: overrideReason,
  });
  if (res.error) fail(t.id, res.error.message);
  if (action === "start_position" && t.state === "thesis") {
    const err = await setState(t.id, { state: "position" });
    if (err) fail(t.id, err);
  }
  done(t.id, action === "start_position" ? "Position recorded in the journal." : "Journal entry added.");
}

export async function decideReview(form: FormData): Promise<void> {
  const t = await load(form);
  const reviewId = field(form, "review_id");
  const verdict = VERDICTS.find((v) => v === field(form, "verdict"));
  const note = field(form, "note");
  if (!UUID.test(reviewId)) fail(t.id, "That review isn't valid.");
  if (verdict === undefined) fail(t.id, "Pick intact, weakened or broken.");
  const res = await db().from("reviews").update({ verdict, note: note || null, decided_at: new Date().toISOString() })
    .eq("id", reviewId).eq("thesis_id", t.id).is("verdict", null).select("id");
  if (res.error) fail(t.id, res.error.message);
  if ((res.data ?? []).length === 0) fail(t.id, "That review was already decided.");
  if (field(form, "to_journal") === "on" && note.length > 0) {
    const j = await db().from("journal").insert({
      thesis_id: t.id, entry_date: new Date().toISOString().slice(0, 10), action: "review", reason: note,
    });
    if (j.error) fail(t.id, j.error.message);
  }
  const next = afterVerdict(t.state, verdict, positionOpen(await journalOf(t.id)));
  if (next !== t.state) {
    const err = await setState(t.id, { state: next });
    if (err) fail(t.id, err);
  }
  done(t.id, verdict === "broken" ? "Marked broken: close it with a post-mortem." : `Marked ${verdict}.`);
}

export async function close(form: FormData): Promise<void> {
  const t = await load(form);
  const whatHappened = field(form, "what_happened");
  const signals = field(form, "signals");
  const lessons = field(form, "lessons");
  const right = field(form, "thesis_right");
  if (!canMove(t.state, "close")) fail(t.id, "Only a thesis, a position or a review can be closed.");
  if (positionOpen(await journalOf(t.id))) fail(t.id, "Record the exit in the journal before closing.");
  if (whatHappened.length === 0 || signals.length === 0 || lessons.length === 0) {
    fail(t.id, "The post-mortem needs what happened, what the signals said and the lessons.");
  }
  const pm = await db().from("postmortems").insert({
    thesis_id: t.id,
    what_happened: whatHappened,
    thesis_right: right === "yes" ? true : right === "no" ? false : null,
    signals_right: { note: signals },
    lessons,
  });
  if (pm.error) fail(t.id, pm.error.message);
  const err = await setState(t.id, { state: "closed" });
  if (err) fail(t.id, err);
  done(t.id, "Closed with a post-mortem.");
}
