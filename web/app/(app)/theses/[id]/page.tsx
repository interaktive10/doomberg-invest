import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { Callout } from "@/components/callout";
import { Chip, Dot } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Icon } from "@/components/icons";
import { KillList } from "@/components/kill-list";
import { Markdown } from "@/components/markdown";
import { ReviewDiff } from "@/components/review-diff";
import { Empty, Flash, FRAME, Note, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { STATE_BADGE } from "@/components/thesis-list";
import { TickerTile } from "@/components/ticker-tile";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { choiceChip, Input, Label, Select, Textarea } from "@/components/ui/input";
import { citeView, factOrder, stripSection, stripTitle, unlabel } from "@/lib/cards";
import { ensureReviews, journal, killCriteria, postmortem, reviews, setting, thesis as getThesis, thesisTitle } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { localToday, thesisWeeks } from "@/lib/discipline";
import { cardSections, caseLine, plainText } from "@/lib/explain";
import { code, num } from "@/lib/format";
import { byEntryDate } from "@/lib/journal";
import { one, UUID, type Query } from "@/lib/forms";
import { ACTION_LABEL, label } from "@/lib/labels";
import type { Tone } from "@/lib/palette";
import type { PackDiff } from "@/lib/reviews";
import { acceptable, canMove, killCheckLine, markMoved, positionOpen, RESEARCH_QUEUED, showsReviews, STATE_LABEL } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { accept, addJournal, close, decideReview, dismissThesis } from "./actions";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Theses: the thesis page, redrawn (overhaul PR 6). A header sheet with the case in one line and where the
// thesis stands; the card as readable sections (its lead, then Facts, Why it may be mispriced, ... each under its own
// title, citations linking to the evidence); What would kill it as a checklist; the reviews, the open one unfolded;
// the private journal; and the §1.8 moves (accept, dismiss, start a position, review verdicts, close with a
// post-mortem), each form behind its button and left out when it can't be used (overhaul PR 4). A section that can't
// fill (Reviews on a card or a closed thesis, no kill criteria) is left out rather than promising what won't come, and
// each header chip is one run of text (PR 6 final review).

/** A form behind a button: a native disclosure whose summary looks like one (no script). */
const OPENER = "list-none [&::-webkit-details-marker]:hidden";

/** The dot before a card section's title. */
const SECTION_TONE: Record<string, Tone> = {
  facts: "text",
  "why it may be mispriced": "gap",
  inferences: "evidence",
  assumptions: "warn",
  risks: "down",
};

function Hidden({ id }: { id: string }) {
  return <input type="hidden" name="thesis_id" value={id} />;
}

/** A date as the screens say it ("Nov 14, 2026"), the ISO date kept for machines. */
function Day({ iso, className }: { iso: string; className?: string }) {
  return (
    <time dateTime={iso.slice(0, 10)} className={cn("num", className)}>
      {shortDate(iso, true)}
    </time>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="eyebrow">{title}</h3>
      <p className="text-[15px] whitespace-pre-wrap text-fg">{children}</p>
    </div>
  );
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
  // The card's own kill-criteria table repeats the live checklist (which adds each one's status), and its title
  // repeats this page's header.
  const card = kills.length > 0 ? stripSection(stripTitle(t.card_md), "Kill criteria") : stripTitle(t.card_md);
  const cited = factOrder(card);
  const cite = (cid: string) => citeView(cid, t.company_id, cited);
  const parts = cardSections(card);
  // The rendered card leads with its summary (pipeline/thesis/render.py): the header shows it as the case, and the
  // card starts at its first section, unless the summary is all the card has.
  const summary = caseLine(t.card_json, t.card_md);
  const leadIsSummary = parts.lead !== "" && plainText(parts.lead) === summary;
  const line = leadIsSummary && parts.sections.length === 0 ? null : summary;
  const lead = leadIsSummary && parts.sections.length > 0 ? "" : parts.lead;
  const triggered = kills.filter((k) => k.status === "triggered").length;
  const writable = t.state !== "dismissed" && t.state !== "closed";
  return (
    <main id="main" className={cn(FRAME, "flex flex-col gap-6 pt-3 pb-8 md:pt-4")}>
      <Link href="/theses" className="inline-flex min-h-11 items-center gap-1.5 self-start text-[14px] font-medium no-underline md:min-h-0">
        <Icon name="chevron-left" />
        Theses
      </Link>

      <header className="sheet rise flex flex-col gap-4 p-5 md:p-7">
        <div className="flex flex-wrap items-center gap-4 md:gap-5">
          <TickerTile ticker={c ? code(c) : "?"} size="lg" />
          <div className="flex min-w-[min(100%,16rem)] flex-1 flex-col gap-1.5">
            <h1 className="text-[28px] leading-[1.15] font-bold tracking-[-0.03em] text-fg md:text-[34px]">
              {c ? c.name : "Thesis"}
              {c ? <span className="sr-only"> ({code(c)})</span> : null}{" "}
              <Badge variant={STATE_BADGE[t.state]} className="ml-1 h-7 px-3 align-middle text-[13px] tracking-normal">
                {STATE_LABEL[t.state]}
              </Badge>
            </h1>
            {line ? <p className="max-w-[620px] text-[16px] leading-normal text-fg">{line}</p> : null}
          </div>
          <Link href={`/company/${t.company_id}`} className={cn(buttonVariants({ variant: "secondary" }), "w-full sm:w-auto")}>
            Company page
          </Link>
        </div>
        <ul aria-label="Where it stands" className="flex flex-wrap gap-2">
          <li>
            {/* one text span per chip, so the chip's gap sits between its icon and its words only (PR 6 final review V4-4) */}
            <Chip title={`Written by: ${t.author}`}>
              <Icon name="doc" className="size-3.5" />
              <span>
                Card of <Day iso={t.created_week} />
              </span>
            </Chip>
          </li>
          {t.accepted_at ? (
            <li>
              <Chip>
                <span>
                  Accepted <Day iso={t.accepted_at} />
                  {weeks <= 0 ? ", this week" : `, ${weeks} ${weeks === 1 ? "week" : "weeks"} ago`}
                </span>
              </Chip>
            </li>
          ) : null}
          {t.next_review ? (
            <li>
              <Chip>
                <Icon name="calendar" className="size-3.5" />
                <span>
                  Next review <Day iso={t.next_review} />
                </span>
              </Chip>
            </li>
          ) : null}
          {open ? (
            <li>
              <Chip variant="good">Position open</Chip>
            </li>
          ) : null}
          {kills.length > 0 ? (
            <li>
              <Chip variant={triggered > 0 ? "bad" : "good"}>
                <Icon name="shield" className="size-3.5" />
                <span>
                  Kill criteria:{" "}
                  <span className="num">
                    {triggered} of {kills.length}
                  </span>{" "}
                  triggered
                </span>
              </Chip>
            </li>
          ) : null}
        </ul>
      </header>

      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      {t.dismissed_reason ? (
        <Callout>
          <span className="font-semibold text-fg">Dismissed:</span> {t.dismissed_reason}
        </Callout>
      ) : null}

      {canMove(t.state, "accept") ? (
        <Section title="Decide" id="decide" description="Watch it, or pass with a reason.">
          <div className="flex flex-wrap items-start gap-3">
            {acceptable(t) ? (
              <form action={accept}>
                <Hidden id={t.id} />
                <SubmitButton>Accept as thesis</SubmitButton>
              </form>
            ) : (
              <Callout className="basis-full">
                No validated card yet: Sunday&apos;s routine writes it.
                <Disclosure summary="Why">
                  A thesis needs the card&apos;s kill criteria and review dates, so it can&apos;t be accepted before the card. The routine
                  writes it after the week&apos;s shortlist.
                </Disclosure>
              </Callout>
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

      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
          {pm ? (
            <Section title="Post-mortem" id="postmortem">
              <div className="flex flex-col gap-4">
                {/* as the Journal says it (PR 6 final review L5-13) */}
                <Chip variant={pm.thesis_right === null ? "plain" : pm.thesis_right ? "good" : "bad"} size="sm" className="self-start">
                  {pm.thesis_right === null ? "Unclear" : pm.thesis_right ? "Called right" : "Called wrong"}
                </Chip>
                <Block title="What happened">{pm.what_happened}</Block>
                <Block title="What the signals said">{String(pm.signals_right?.note ?? "")}</Block>
                <Block title="Lesson">{pm.lessons}</Block>
              </div>
            </Section>
          ) : null}

          <Section title="Research card" id="card">
            {t.card_md.trim() && !lead && parts.sections.length === 0 ? (
              <Empty>The card has nothing beyond its kill criteria.</Empty>
            ) : t.card_md.trim() ? (
              <div className="flex flex-col gap-5">
                {lead ? (
                  <div className="[&_.prose-md]:text-[17px]">
                    <Markdown text={lead} cite={cite} />
                  </div>
                ) : null}
                {parts.sections.map((s, i) => (
                  <div key={`${i}-${s.title}`} className="flex flex-col gap-1.5 border-t border-line pt-4 first:border-t-0 first:pt-0">
                    <h3 className="flex items-center gap-2 text-[17px] font-bold tracking-[-0.01em] text-fg">
                      <Dot tone={SECTION_TONE[s.title.toLowerCase()] ?? "muted"} className="size-2.5" />
                      {s.title}
                    </h3>
                    <Markdown text={unlabel(s.title, s.body)} cite={cite} />
                  </div>
                ))}
              </div>
            ) : (
              <Empty>
                {t.state === "research"
                  ? `No card yet. ${RESEARCH_QUEUED} It writes a grounded card for this research entry after the week's shortlist.`
                  : "No card: this research entry closed before the routine wrote one."}
              </Empty>
            )}
          </Section>

          {showsReviews(t.state, revs.length) ? (
            <Section title="Reviews" id="reviews" count={revs.length}>
              {revs.length === 0 ? (
                <Empty>No review yet. One comes after each new quarterly filing.</Empty>
              ) : (
                <ul className="flex flex-col gap-3">
                  {revs.map((r) => (
                    <li key={r.id} className="tile flex flex-col gap-2 p-4">
                      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                        <span className="text-[15px] font-semibold text-fg">
                          {r.period_end ? (
                            <>
                              Quarter to <Day iso={r.period_end} />
                            </>
                          ) : (
                            "A kill criterion triggered"
                          )}
                        </span>
                        <span className="text-[13px] text-subtle">
                          created <Day iso={r.created_at} />
                        </span>
                        {r.verdict ? (
                          <Badge variant={r.verdict === "broken" ? "destructive" : r.verdict === "weakened" ? "warning" : "success"}>{r.verdict}</Badge>
                        ) : (
                          <Badge variant="warning">waiting for a verdict</Badge>
                        )}
                      </div>
                      <Disclosure summary="What changed" open={r.verdict === null}>
                        <ReviewDiff id={r.period_end ?? r.created_at.slice(0, 10)} diff={r.pack_diff as Partial<PackDiff>} />
                      </Disclosure>
                      {r.note ? (
                        <p className="text-[14px] text-fg">
                          <span className="font-semibold">Note:</span> {r.note}
                        </p>
                      ) : null}
                      {r.verdict === null && t.state === "review" ? (
                        <details className="mt-1 border-t border-line pt-3">
                          <summary className={cn(buttonVariants({ size: "sm" }), OPENER)}>Record a verdict</summary>
                          <form action={decideReview} className="mt-3 flex flex-col gap-3">
                            <Hidden id={t.id} />
                            <input type="hidden" name="review_id" value={r.id} />
                            <fieldset className="min-w-0">
                              <legend className="mb-2 text-[13px] font-medium text-muted">Verdict</legend>
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
                            <label className="flex min-h-11 items-center gap-2 text-[14px] md:min-h-0">
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
          ) : null}
        </div>

        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">
          {kills.length > 0 ? (
            <Section title="What would kill it" id="kill" description={killCheckLine(kills)}>
              <KillList kills={kills} detail />
            </Section>
          ) : null}

          <Section title="Journal" id="journal" description="Private: never sent to any LLM.">
            {entries.length === 0 ? (
              <Empty>No journal entries for this thesis.</Empty>
            ) : (
              <ul aria-label="Journal entries" className="flex flex-col">
                {byEntryDate(entries).map((e) => (
                  <li key={e.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0 first:pt-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                      <span className="font-semibold text-fg">{label(ACTION_LABEL, e.action)}</span>
                      <Day iso={e.entry_date} className="text-subtle" />
                      {e.portfolio_pct === null ? null : (
                        <Chip size="sm">
                          <span>
                            <span className="num">{num(e.portfolio_pct)}%</span> of portfolio
                          </span>
                        </Chip>
                      )}
                    </div>
                    <p className="text-[14px] break-words whitespace-pre-wrap text-fg">{e.reason}</p>
                    {e.override_reason ? <p className="text-[13px] break-words text-warn">Override: {e.override_reason}</p> : null}
                  </li>
                ))}
              </ul>
            )}
            {writable ? (
              <details className="mt-4">
                <summary className={cn(buttonVariants({ variant: "outline", size: "sm" }), OPENER)}>Add a journal entry</summary>
                <form action={addJournal} className="mt-3 grid grid-cols-1 gap-4">
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
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="j-reason">Reason</Label>
                    <Textarea id="j-reason" name="reason" required />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="j-override">Override reason (a position before the thesis is {num(minWeeks, 0)} weeks old)</Label>
                    <Textarea id="j-override" name="override_reason" className="min-h-16" />
                    <Note>
                      The thesis is {weeks} {weeks === 1 ? "week" : "weeks"} old; starting a position needs {num(minWeeks, 0)}, or an override reason.
                    </Note>
                  </div>
                  <div>
                    <SubmitButton>Add entry</SubmitButton>
                  </div>
                </form>
              </details>
            ) : null}
          </Section>

          {canMove(t.state, "close") ? (
            <Section title="Close" id="close" description="Closing is final: write down what happened while it's fresh.">
              {open ? (
                <Callout>A position is open: record the exit in the journal before closing.</Callout>
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
                      <legend className="mb-2 text-[13px] font-medium text-muted">Was the thesis right?</legend>
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
        </div>
      </div>
    </main>
  );
}
