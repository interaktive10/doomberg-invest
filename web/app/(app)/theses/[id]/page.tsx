import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/components/markdown";
import { ReviewDiff } from "@/components/review-diff";
import { Empty, Flash, Note, Page, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { citeView, factOrder, stripSection, stripTitle } from "@/lib/cards";
import { ensureReviews, journal, killCriteria, postmortem, reviews, setting, thesis as getThesis, thesisTitle } from "@/lib/data";
import { localToday, thesisWeeks } from "@/lib/discipline";
import { code, measure, num } from "@/lib/format";
import { one, UUID, type Query } from "@/lib/forms";
import { ACTION_LABEL, label } from "@/lib/labels";
import type { PackDiff } from "@/lib/reviews";
import { acceptable, canMove, markMoved, positionOpen, STATE_LABEL } from "@/lib/theses";
import { accept, addJournal, close, decideReview, dismissThesis } from "./actions";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Theses: the thesis page with the card, kill-criteria status, review history and journal entries, plus the
// §1.8 moves (accept, dismiss, start a position, review verdicts, close with a post-mortem).

const OPS: Record<string, string> = { "<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=", changes: "changes" }; // pipeline/thesis/render.py

const STATE_BADGE = {
  research: "secondary",
  thesis: "default",
  position: "success",
  review: "warning",
  closed: "outline",
  dismissed: "outline",
} as const;

const choice =
  "flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm has-checked:border-blue-700 has-checked:bg-blue-50";

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
          {open ? " · position open" : ""} · <Link href={`/company/${t.company_id}`}>company page</Link>
        </p>
      }
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      {t.dismissed_reason ? (
        <p className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm">
          <span className="font-medium">Dismissed:</span> {t.dismissed_reason}
        </p>
      ) : null}

      {canMove(t.state, "accept") ? (
        <Section title="Decide" id="decide" description="Accept to watch its kill criteria and review it after each filing, or dismiss it with a reason.">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
            {acceptable(t) ? (
              <form action={accept}>
                <Hidden id={t.id} />
                <SubmitButton>Accept as thesis</SubmitButton>
              </form>
            ) : (
              <p className="max-w-md text-sm">
                Manual research: there is no validated card yet, so this can&apos;t become a thesis (a thesis needs the card&apos;s
                kill criteria and review dates). The weekly routine writes cards for the week&apos;s shortlist.
              </p>
            )}
            <form action={dismissThesis} className="flex flex-wrap items-end gap-2">
              <Hidden id={t.id} />
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dismiss-reason">Reason to dismiss</Label>
                <Input id="dismiss-reason" name="reason" required className="w-64 max-w-full" />
              </div>
              <SubmitButton variant="outline">Dismiss</SubmitButton>
            </form>
          </div>
        </Section>
      ) : null}

      <Section title="Card" id="card" description={t.card_md.trim() ? "Citations link to the evidence on the company page." : undefined}>
        {t.card_md.trim() ? (
          <Markdown text={card} cite={(cid) => citeView(cid, t.company_id, cited)} />
        ) : (
          <Empty>No card yet: manual research. The weekly routine writes cards for the shortlist.</Empty>
        )}
      </Section>

      <Section title="Kill criteria" id="kill" description="Evaluated against the latest filed figures; a triggered one sends the thesis to Review.">
        {kills.length === 0 ? (
          <Empty>No kill criteria.</Empty>
        ) : (
          <Table label="Kill criteria">
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Condition</TableHead>
                <TableHead>Check after</TableHead>
                <TableHead>Status</TableHead>
                <TableHead num>Last value</TableHead>
                <TableHead>Checked</TableHead>
                <TableHead>Why</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {kills.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>
                    <code>{k.metric}</code>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {OPS[k.operator] ?? k.operator} {k.threshold ?? ""}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">{k.check_after}</TableCell>
                  <TableCell>
                    <Badge variant={k.status === "triggered" ? "destructive" : k.status === "ok" ? "success" : "secondary"}>{k.status}</Badge>
                  </TableCell>
                  <TableCell num>{measure(k.last_value)}</TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">{k.last_checked ?? ""}</TableCell>
                  <TableCell className="max-w-sm min-w-48">{k.why ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      <Section title="Reviews" id="reviews">
        {revs.length === 0 ? (
          <Empty>No review yet. One is created after each new quarterly filing.</Empty>
        ) : (
          <ul className="flex flex-col gap-3">
            {revs.map((r) => (
              <li key={r.id} className="rounded-lg border border-gray-200 p-3 sm:p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-sm font-medium">
                  <span>{r.period_end ? `Quarter ${r.period_end}` : "A kill criterion triggered"}</span>
                  <span className="font-normal text-gray-700">· created {r.created_at.slice(0, 10)}</span>
                  {r.verdict ? (
                    <Badge variant={r.verdict === "broken" ? "destructive" : r.verdict === "weakened" ? "warning" : "success"}>{r.verdict}</Badge>
                  ) : (
                    <Badge variant="warning">waiting for a verdict</Badge>
                  )}
                </div>
                <ReviewDiff id={r.period_end ?? r.created_at.slice(0, 10)} diff={r.pack_diff as Partial<PackDiff>} />
                {r.note ? <p className="mt-3 text-sm">Note: {r.note}</p> : null}
                {r.verdict === null && t.state === "review" ? (
                  <form action={decideReview} className="mt-4 flex flex-col gap-3 border-t border-gray-200 pt-4">
                    <Hidden id={t.id} />
                    <input type="hidden" name="review_id" value={r.id} />
                    <fieldset className="min-w-0">
                      <legend className="mb-2 text-sm font-medium">Verdict</legend>
                      <div className="flex flex-wrap gap-2">
                        {(["intact", "weakened", "broken"] as const).map((v) => (
                          <label key={v} className={choice}>
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
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" name="to_journal" /> Also add the note to the journal
                    </label>
                    <div>
                      <SubmitButton>Record verdict</SubmitButton>
                    </div>
                  </form>
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
                  <TableCell className="whitespace-nowrap tabular-nums">{e.entry_date}</TableCell>
                  <TableCell className="whitespace-nowrap">{label(ACTION_LABEL, e.action)}</TableCell>
                  <TableCell num>{e.portfolio_pct === null ? "" : `${num(e.portfolio_pct)}%`}</TableCell>
                  <TableCell className="max-w-md min-w-48 break-words">{e.reason}</TableCell>
                  <TableCell className="max-w-xs break-words">{e.override_reason ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {t.state !== "dismissed" ? (
          <form action={addJournal} className="mt-4 grid grid-cols-1 gap-4 rounded-lg border border-gray-200 bg-gray-50 p-4 md:grid-cols-2">
            <Hidden id={t.id} />
            <h3 className="font-semibold md:col-span-2">Add a journal entry</h3>
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
        ) : null}
      </Section>

      {canMove(t.state, "close") ? (
        <Section title="Close with a post-mortem" id="close" description="Closing is final: write down what happened while it's fresh.">
          <form action={close} className="grid grid-cols-1 gap-4">
            <Hidden id={t.id} />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pm-what">What happened, compared with the thesis</Label>
              <Textarea id="pm-what" name="what_happened" required />
            </div>
            <fieldset className="min-w-0">
              <legend className="mb-2 text-sm font-medium">Was the thesis right?</legend>
              <div className="flex flex-wrap gap-2">
                {(["yes", "no", "unclear"] as const).map((v) => (
                  <label key={v} className={choice}>
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
        </Section>
      ) : null}

      {pm ? (
        <Section title="Post-mortem" id="postmortem">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)]">
            <dt className="font-medium text-gray-700">What happened</dt>
            <dd className="whitespace-pre-wrap">{pm.what_happened}</dd>
            <dt className="font-medium text-gray-700">Thesis right?</dt>
            <dd>{pm.thesis_right === null ? "unclear" : pm.thesis_right ? "yes" : "no"}</dd>
            <dt className="font-medium text-gray-700">What the signals said</dt>
            <dd className="whitespace-pre-wrap">{String(pm.signals_right?.note ?? "")}</dd>
            <dt className="font-medium text-gray-700">Lessons</dt>
            <dd className="whitespace-pre-wrap">{pm.lessons}</dd>
          </dl>
        </Section>
      ) : null}
    </Page>
  );
}
