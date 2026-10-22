import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/components/markdown";
import { ReviewDiff } from "@/components/review-diff";
import { Empty, Flash, Note, Page, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { choiceChip, Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { citeView, factOrder, stripSection, stripTitle } from "@/lib/cards";
import { ensureReviews, journal, killCriteria, postmortem, reviews, setting, thesis as getThesis, thesisTitle } from "@/lib/data";
import { localToday, thesisWeeks } from "@/lib/discipline";
import { code, num } from "@/lib/format";
import { one, UUID, type Query } from "@/lib/forms";
import { ACTION_LABEL, killMetric, killSentence, label, metricValue } from "@/lib/labels";
import type { PackDiff } from "@/lib/reviews";
import { acceptable, canMove, markMoved, positionOpen, RESEARCH_QUEUED, STATE_LABEL } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { accept, addJournal, close, decideReview, dismissThesis } from "./actions";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Theses: the thesis page with the card, kill criteria in words with their status, review history and
// journal entries, plus the §1.8 moves (accept, dismiss, start a position, review verdicts, close with a
// post-mortem). Overhaul PR 4: no ribbon; each form opens from its button and is left out when it can't be used.

/** A form behind a button: a native disclosure whose summary looks like one (no script). */
const OPENER = "list-none [&::-webkit-details-marker]:hidden";

const STATE_BADGE = {
  research: "secondary",
  thesis: "default",
  position: "success",
  review: "warning",
  closed: "outline",
  dismissed: "outline",
} as const;

function Hidden({ id }: { id: string }) {
  return <input type="hidden" name="thesis_id" value={id} />;
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const c = UUID.test(id) ? await thesisTitle(id) : null;
  return { title: c ? `${c.name} (${code(c)}) · thesis` : "Thesis" };
}

export default async function ThesisPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const { id } = await params;
  const q = await searchParams;
  if (!UUID.test(id)) notFound();
  const first = await getThesis(id);
  if (first === null) notFound();
  const [t] = markMoved([first], await ensureReviews([first]));
  if (t === undefined) notFound();
  const [kills, revs, entries, pm, minWeeks] = await Promise.all([
    killCriteria(id),
    reviews(id),
    journal(id),
    postmortem(id),
    setting<number | string>("position_min_thesis_weeks", 4),
  ]);
  const c = t.companies;
  const open = positionOpen(entries);
  const weeks = thesisWeeks(t.accepted_at, t.created_week, new Date());
  const today = localToday(new Date());
  // The card's own kill-criteria table repeats the live one below (which adds each one's status), and its title
  // repeats this page's header.
  const card = kills.length > 0 ? stripSection(stripTitle(t.card_md), "Kill criteria") : stripTitle(t.card_md);
  const cited = factOrder(card);
  const triggered = kills.filter((k) => k.status === "triggered").length;
  return (
    <Page
      title={
        <>
          {c ? `${c.name} (${code(c)})` : "Thesis"}{" "}
          <Badge variant={STATE_BADGE[t.state]} className="ml-1 align-middle text-sm">
            {STATE_LABEL[t.state]}
          </Badge>
        </>
      }
      description={
        <p>
          Card week {t.created_week} · {t.author}
          {t.accepted_at ? ` · accepted ${t.accepted_at.slice(0, 10)} (${weeks} week(s) ago)` : ""}
          {t.next_review ? ` · next review ${t.next_review}` : ""}
          {open ? " · position open" : ""}
          {kills.length > 0 ? ` · kill criteria ${triggered} of ${kills.length} triggered` : ""} ·{" "}
          <Link href={`/company/${t.company_id}`}>company page</Link>
        </p>
      }
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      {t.dismissed_reason ? (
        <p className="rounded-md border border-line bg-panel px-4 py-3 text-[13px]">
          <span className="font-medium">Dismissed:</span> {t.dismissed_reason}
        </p>
      ) : null}

      {canMove(t.state, "accept") ? (
        <Section
          title="Decide"
          id="decide"
          description="Accept to watch its kill criteria and review it after each filing, or dismiss it with a reason."
          className="border-l-2 border-l-accent"
        >
          <div className="flex flex-wrap items-start gap-x-3 gap-y-3">
            {acceptable(t) ? (
              <form action={accept}>
                <Hidden id={t.id} />
                <SubmitButton>Accept as thesis</SubmitButton>
              </form>
            ) : (
              <p className="max-w-md basis-full text-[13px] text-muted">
                There is no validated card yet, so this can&apos;t become a thesis (a thesis needs the card&apos;s kill criteria and
                review dates). Sunday&apos;s routine writes the card for a research entry, after the week&apos;s shortlist.
              </p>
            )}
            <details>
              <summary className={cn(buttonVariants({ variant: "outline" }), OPENER)}>Dismiss</summary>
              <form action={dismissThesis} className="mt-3 flex flex-wrap items-end gap-2">
                <Hidden id={t.id} />
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="dismiss-reason">Reason to dismiss</Label>
                  <Input id="dismiss-reason" name="reason" required className="w-64 max-w-full" />
                </div>
                <SubmitButton variant="outline">Confirm dismissal</SubmitButton>
              </form>
            </details>
          </div>
        </Section>
      ) : null}

      <Section title="Card" id="card" description={t.card_md.trim() ? "Citations link to the evidence on the company page." : undefined}>
        {t.card_md.trim() ? (
          <Markdown text={card} cite={(cid) => citeView(cid, t.company_id, cited)} />
        ) : (
          <Empty>
            {t.state === "research"
              ? `No card yet. ${RESEARCH_QUEUED} It writes a grounded card for this research entry after the week's shortlist.`
              : "No card: this research entry closed before the routine wrote one."}
          </Empty>
        )}
      </Section>

      <Section title="Kill criteria" id="kill" description="Evaluated against the latest filed figures; a triggered one sends the thesis to Review.">
        {kills.length === 0 ? (
          <Empty>No kill criteria.</Empty>
        ) : (
          <ul aria-label="Kill criteria" className="flex flex-col gap-2">
            {kills.map((k) => (
              <li key={k.id} className="rounded-sm border border-line bg-canvas p-3 text-[13px]">
                <div className="flex flex-wrap items-start gap-2">
                  <Badge variant={k.status === "triggered" ? "destructive" : k.status === "ok" ? "success" : "secondary"}>{k.status}</Badge>
                  <span className="min-w-0 flex-1 text-fg">{killSentence(k)}</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  Now <span className="num">{metricValue(k.last_value, killMetric(k.metric).unit)}</span>
                  {k.last_checked ? (
                    <>
                      , checked week <span className="num">{k.last_checked}</span>
                    </>
                  ) : null}
                  {k.triggered_week ? (
                    <>
                      ; triggered week <span className="num">{k.triggered_week}</span>
                    </>
                  ) : null}
                  .{k.why ? ` Why: ${k.why}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Reviews" id="reviews">
        {revs.length === 0 ? (
          <Empty>No review yet. One is created after each new quarterly filing.</Empty>
        ) : (
          <ul className="flex flex-col gap-3">
            {revs.map((r) => (
              <li key={r.id} className="rounded-sm border border-line bg-canvas p-3 sm:p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-sm font-medium">
                  <span>{r.period_end ? `Quarter ${r.period_end}` : "A kill criterion triggered"}</span>
                  <span className="font-normal text-muted">
                    · created <span className="num">{r.created_at.slice(0, 10)}</span>
                  </span>
                  {r.verdict ? (
                    <Badge variant={r.verdict === "broken" ? "destructive" : r.verdict === "weakened" ? "warning" : "success"}>{r.verdict}</Badge>
                  ) : (
                    <Badge variant="warning">waiting for a verdict</Badge>
                  )}
                </div>
                <ReviewDiff id={r.period_end ?? r.created_at.slice(0, 10)} diff={r.pack_diff as Partial<PackDiff>} />
                {r.note ? <p className="mt-3 text-[13px]">Note: {r.note}</p> : null}
                {r.verdict === null && t.state === "review" ? (
                  <details className="mt-4 border-t border-line pt-4">
                    <summary className={cn(buttonVariants({ size: "sm" }), OPENER)}>Record a verdict</summary>
                    <form action={decideReview} className="mt-3 flex flex-col gap-3">
                      <Hidden id={t.id} />
                      <input type="hidden" name="review_id" value={r.id} />
                      <fieldset className="min-w-0">
                        <legend className="mb-2 text-xs font-medium text-muted">Verdict</legend>
                        <div className="flex flex-wrap gap-2">
                          {(["intact", "weakened", "broken"] as const).map((v) => (
                            <label key={v} className={choiceChip}>
                              <input type="radio" name="verdict" value={v} required />
                              {v}
                            </label>
                          ))}
                        </div>
                      </fieldset>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor={`note-${r.id}`}>Note</Label>
                        <Textarea id={`note-${r.id}`} name="note" />
                      </div>
                      <label className="flex items-center gap-2 text-[13px]">
                        <input type="checkbox" name="to_journal" /> Also add the note to the journal
                      </label>
                      <div>
                        <SubmitButton>Record verdict</SubmitButton>
                      </div>
                    </form>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Journal" id="journal" description="Private: never sent to any LLM.">
        {entries.length === 0 ? (
          <Empty>No journal entries for this thesis.</Empty>
        ) : (
          <Table label="Journal entries">
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Action</TableHead>
                <TableHead num>% of portfolio</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Override</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="num whitespace-nowrap">{e.entry_date}</TableCell>
                  <TableCell className="whitespace-nowrap">{label(ACTION_LABEL, e.action)}</TableCell>
                  <TableCell num>{e.portfolio_pct === null ? "" : `${num(e.portfolio_pct)}%`}</TableCell>
                  <TableCell className="max-w-md min-w-48 break-words">{e.reason}</TableCell>
                  <TableCell className="max-w-xs break-words">{e.override_reason ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {t.state !== "dismissed" && t.state !== "closed" ? (
          <details className="mt-4">
            <summary className={cn(buttonVariants({ variant: "outline", size: "sm" }), OPENER)}>Add a journal entry</summary>
            <form action={addJournal} className="mt-3 grid grid-cols-1 gap-4 rounded-sm border border-line bg-canvas p-3 sm:p-4 md:grid-cols-2">
              <Hidden id={t.id} />
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="j-action">Action</Label>
                <Select id="j-action" name="action" defaultValue={t.state === "thesis" && !open ? "start_position" : "note"}>
                  {(["note", "start_position", "add", "trim", "exit", "review"] as const).map((a) => (
                    <option key={a} value={a}>
                      {ACTION_LABEL[a]}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="j-date">Date</Label>
                <Input id="j-date" name="entry_date" type="date" defaultValue={today} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="j-pct">% of portfolio (optional)</Label>
                <Input id="j-pct" name="portfolio_pct" type="number" step="0.1" min="0" max="100" inputMode="decimal" />
              </div>
              <div className="flex flex-col gap-1.5 md:col-span-2">
                <Label htmlFor="j-reason">Reason</Label>
                <Textarea id="j-reason" name="reason" required />
              </div>
              <div className="flex flex-col gap-1.5 md:col-span-2">
                <Label htmlFor="j-override">Override reason (a position before the thesis is {num(minWeeks, 0)} weeks old)</Label>
                <Textarea id="j-override" name="override_reason" className="min-h-16" />
                <Note>
                  Discipline rule (§11.9): the thesis is {weeks} week(s) old; a start-position entry needs {num(minWeeks, 0)}, or an override
                  reason.
                </Note>
              </div>
              <div className="md:col-span-2">
                <SubmitButton>Add entry</SubmitButton>
              </div>
            </form>
          </details>
        ) : null}
      </Section>

      {canMove(t.state, "close") ? (
        <Section title="Close" id="close" description="Closing is final: write down what happened while it's fresh.">
          {open ? (
            <p className="text-[13px] text-muted">A position is open: record the exit in the journal before closing.</p>
          ) : (
            <details>
              <summary className={cn(buttonVariants({ variant: "outline", size: "sm" }), OPENER)}>Close with a post-mortem</summary>
              <form action={close} className="mt-3 grid grid-cols-1 gap-4">
                <Hidden id={t.id} />
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-what">What happened, compared with the thesis</Label>
                  <Textarea id="pm-what" name="what_happened" required />
                </div>
                <fieldset className="min-w-0">
                  <legend className="mb-2 text-xs font-medium text-muted">Was the thesis right?</legend>
                  <div className="flex flex-wrap gap-2">
                    {(["yes", "no", "unclear"] as const).map((v) => (
                      <label key={v} className={choiceChip}>
                        <input type="radio" name="thesis_right" value={v} defaultChecked={v === "unclear"} />
                        {v}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-signals">What the signals said</Label>
                  <Textarea id="pm-signals" name="signals" required />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-lessons">Lessons</Label>
                  <Textarea id="pm-lessons" name="lessons" required />
                </div>
                <div>
                  <SubmitButton variant="destructive">Close thesis</SubmitButton>
                </div>
              </form>
            </details>
          )}
        </Section>
      ) : null}

      {pm ? (
        <Section title="Post-mortem" id="postmortem">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)]">
            <dt className="font-medium text-muted">What happened</dt>
            <dd className="whitespace-pre-wrap">{pm.what_happened}</dd>
            <dt className="font-medium text-muted">Thesis right?</dt>
            <dd>{pm.thesis_right === null ? "unclear" : pm.thesis_right ? "yes" : "no"}</dd>
            <dt className="font-medium text-muted">What the signals said</dt>
            <dd className="whitespace-pre-wrap">{String(pm.signals_right?.note ?? "")}</dd>
            <dt className="font-medium text-muted">Lessons</dt>
            <dd className="whitespace-pre-wrap">{pm.lessons}</dd>
          </dl>
        </Section>
      ) : null}
    </Page>
  );
}
