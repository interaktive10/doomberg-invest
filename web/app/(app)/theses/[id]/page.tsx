import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/components/markdown";
import { ReviewDiff } from "@/components/review-diff";
import { Empty, Flash, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ensureReviews, journal, killCriteria, postmortem, reviews, setting, thesis as getThesis } from "@/lib/data";
import { localToday, thesisWeeks } from "@/lib/discipline";
import { big, code, num } from "@/lib/format";
import { one, UUID, type Query } from "@/lib/forms";
import type { PackDiff } from "@/lib/reviews";
import { acceptable, canMove, markMoved, positionOpen, STATE_LABEL } from "@/lib/theses";
import { accept, addJournal, close, decideReview, dismissThesis } from "./actions";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Theses: the thesis page with the card, kill-criteria status, review history and journal entries, plus the
// §1.8 moves (accept, dismiss, start a position, review verdicts, close with a post-mortem).

function Hidden({ id }: { id: string }) {
  return <input type="hidden" name="thesis_id" value={id} />;
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
  return (
    <Page
      title={
        <>
          {c ? `${c.name} (${code(c)})` : "Thesis"} <Badge className="align-middle text-sm">{STATE_LABEL[t.state]}</Badge>
        </>
      }
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <p className="text-sm text-gray-700">
        Card week {t.created_week} · {t.author}
        {t.accepted_at ? ` · accepted ${t.accepted_at.slice(0, 10)} (${weeks} week(s) ago)` : ""}
        {t.next_review ? ` · next review ${t.next_review}` : ""}
        {open ? " · position open" : ""} · <Link href={`/company/${t.company_id}`}>company page</Link>
      </p>
      {t.dismissed_reason ? <p className="mt-2 text-sm">Dismissed: {t.dismissed_reason}</p> : null}

      {canMove(t.state, "accept") ? (
        <Section title="Decide" id="decide">
          <div className="flex flex-wrap items-start gap-4">
            {acceptable(t) ? (
              <form action={accept}>
                <Hidden id={t.id} />
                <Button type="submit">Accept as thesis</Button>
              </form>
            ) : (
              <p className="max-w-md text-sm">
                Manual research: there is no validated card yet, so this can't become a thesis (a thesis needs the card's
                kill criteria and review dates). The weekly routine writes cards for the week's shortlist.
              </p>
            )}
            <form action={dismissThesis} className="flex flex-wrap items-end gap-2">
              <Hidden id={t.id} />
              <div className="flex flex-col gap-1">
                <Label htmlFor="dismiss-reason">Reason to dismiss</Label>
                <Input id="dismiss-reason" name="reason" required className="w-64" />
              </div>
              <Button type="submit" variant="outline">
                Dismiss
              </Button>
            </form>
          </div>
        </Section>
      ) : null}

      <Section title="Card" id="card">
        {t.card_md.trim() ? <Markdown text={t.card_md} /> : <Empty>No card yet: manual research. The weekly routine writes cards for the shortlist.</Empty>}
      </Section>

      <Section title="Kill criteria" id="kill">
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
                <TableHead>Last value</TableHead>
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
                  <TableCell>
                    {k.operator} {k.threshold ?? ""}
                  </TableCell>
                  <TableCell>{k.check_after}</TableCell>
                  <TableCell>
                    <Badge variant={k.status === "triggered" ? "destructive" : k.status === "ok" ? "success" : "secondary"}>{k.status}</Badge>
                  </TableCell>
                  <TableCell>{k.last_value === null ? "n/a" : num(k.last_value, 4)}</TableCell>
                  <TableCell>{k.last_checked ?? ""}</TableCell>
                  <TableCell className="max-w-sm">{k.why ?? ""}</TableCell>
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
          <ul className="flex flex-col gap-4">
            {revs.map((r) => (
              <li key={r.id} className="rounded-md border border-gray-300 p-3">
                <div className="mb-2 text-sm font-medium">
                  {r.period_end ? `Quarter ${r.period_end}` : "A kill criterion triggered"} · created {r.created_at.slice(0, 10)}{" "}
                  {r.verdict ? <Badge variant={r.verdict === "broken" ? "destructive" : r.verdict === "weakened" ? "warning" : "success"}>{r.verdict}</Badge> : <Badge variant="warning">waiting for a verdict</Badge>}
                </div>
                <ReviewDiff id={r.period_end ?? r.created_at.slice(0, 10)} diff={r.pack_diff as Partial<PackDiff>} />
                {r.note ? <p className="mt-2 text-sm">Note: {r.note}</p> : null}
                {r.verdict === null && t.state === "review" ? (
                  <form action={decideReview} className="mt-3 flex flex-col gap-2">
                    <Hidden id={t.id} />
                    <input type="hidden" name="review_id" value={r.id} />
                    <fieldset className="flex flex-wrap gap-4 text-sm">
                      <legend className="mb-1 font-medium">Verdict</legend>
                      {(["intact", "weakened", "broken"] as const).map((v) => (
                        <label key={v} className="flex items-center gap-1">
                          <input type="radio" name="verdict" value={v} required /> {v}
                        </label>
                      ))}
                    </fieldset>
                    <Label htmlFor={`note-${r.id}`}>Note</Label>
                    <Textarea id={`note-${r.id}`} name="note" />
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" name="to_journal" /> Also add the note to the journal
                    </label>
                    <div>
                      <Button type="submit">Record verdict</Button>
                    </div>
                  </form>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Journal" id="journal">
        {entries.length === 0 ? (
          <Empty>No journal entries for this thesis.</Empty>
        ) : (
          <Table label="Journal entries">
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>% of portfolio</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Override</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>{e.entry_date}</TableCell>
                  <TableCell>{e.action}</TableCell>
                  <TableCell>{e.portfolio_pct === null ? "" : `${num(e.portfolio_pct)}%`}</TableCell>
                  <TableCell className="max-w-md break-words">{e.reason}</TableCell>
                  <TableCell className="max-w-xs break-words">{e.override_reason ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {t.state !== "dismissed" ? (
          <form action={addJournal} className="mt-4 grid gap-3 rounded-md border border-gray-300 p-3 md:grid-cols-2">
            <Hidden id={t.id} />
            <h3 className="font-semibold md:col-span-2">Add a journal entry</h3>
            <div className="flex flex-col gap-1">
              <Label htmlFor="j-action">Action</Label>
              <Select id="j-action" name="action" defaultValue={t.state === "thesis" && !open ? "start_position" : "note"}>
                <option value="note">note</option>
                <option value="start_position">start position</option>
                <option value="add">add</option>
                <option value="trim">trim</option>
                <option value="exit">exit</option>
                <option value="review">review</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="j-date">Date</Label>
              <Input id="j-date" name="entry_date" type="date" defaultValue={today} required />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="j-pct">% of portfolio (optional)</Label>
              <Input id="j-pct" name="portfolio_pct" type="number" step="0.1" min="0" max="100" inputMode="decimal" />
            </div>
            <div className="flex flex-col gap-1 md:col-span-2">
              <Label htmlFor="j-reason">Reason</Label>
              <Textarea id="j-reason" name="reason" required />
            </div>
            <div className="flex flex-col gap-1 md:col-span-2">
              <Label htmlFor="j-override">Override reason (a position before the thesis is {num(minWeeks, 0)} weeks old)</Label>
              <Textarea id="j-override" name="override_reason" />
              <p className="text-xs text-gray-700">
                Discipline rule (§11.9): the thesis is {weeks} week(s) old; a start-position entry needs {num(minWeeks, 0)}, or an override
                reason.
              </p>
            </div>
            <div className="md:col-span-2">
              <Button type="submit">Add entry</Button>
            </div>
          </form>
        ) : null}
      </Section>

      {canMove(t.state, "close") ? (
        <Section title="Close with a post-mortem" id="close">
          <form action={close} className="grid gap-3 rounded-md border border-gray-300 p-3">
            <Hidden id={t.id} />
            <Label htmlFor="pm-what">What happened, compared with the thesis</Label>
            <Textarea id="pm-what" name="what_happened" required />
            <fieldset className="flex flex-wrap gap-4 text-sm">
              <legend className="mb-1 font-medium">Was the thesis right?</legend>
              {(["yes", "no", "unclear"] as const).map((v) => (
                <label key={v} className="flex items-center gap-1">
                  <input type="radio" name="thesis_right" value={v} defaultChecked={v === "unclear"} /> {v}
                </label>
              ))}
            </fieldset>
            <Label htmlFor="pm-signals">What the signals said</Label>
            <Textarea id="pm-signals" name="signals" required />
            <Label htmlFor="pm-lessons">Lessons</Label>
            <Textarea id="pm-lessons" name="lessons" required />
            <div>
              <Button type="submit" variant="destructive">
                Close thesis
              </Button>
            </div>
          </form>
        </Section>
      ) : null}

      {pm ? (
        <Section title="Post-mortem" id="postmortem">
          <dl className="grid gap-2 text-sm">
            <dt className="font-medium">What happened</dt>
            <dd className="whitespace-pre-wrap">{pm.what_happened}</dd>
            <dt className="font-medium">Thesis right?</dt>
            <dd>{pm.thesis_right === null ? "unclear" : pm.thesis_right ? "yes" : "no"}</dd>
            <dt className="font-medium">What the signals said</dt>
            <dd className="whitespace-pre-wrap">{String(pm.signals_right?.note ?? "")}</dd>
            <dt className="font-medium">Lessons</dt>
            <dd className="whitespace-pre-wrap">{pm.lessons}</dd>
          </dl>
        </Section>
      ) : null}
    </Page>
  );
}
