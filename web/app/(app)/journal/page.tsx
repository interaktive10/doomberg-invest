import Link from "next/link";
import { Chip, Dot } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Icon, type IconName } from "@/components/icons";
import { Empty, Flash, Page, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { buttonVariants } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { journal, postmortems, theses, type JournalEntry } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { localToday } from "@/lib/discipline";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { byEntryDate, journalLine, recordLine, signalsNote, trackRecord } from "@/lib/journal";
import { ACTION_LABEL, label } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { addNote } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Journal" };

// BRIEF §6 Journal: private entries and post-mortems. They live only in the database; the web app makes no LLM calls
// and the pipeline's privacy check refuses them (llm/privacy.py). Drawn in overhaul PR 6: each entry a row led by its
// action's icon (newest first by its date), the post-mortems as tiles with the lesson up front and a dot per thesis
// called right or wrong beside the record it draws (PR 6 final review).

const ACTION: Record<JournalEntry["action"], { icon: IconName; ring: string }> = {
  note: { icon: "book", ring: "bg-hover text-muted" },
  start_position: { icon: "plus", ring: "bg-up/10 text-up" },
  add: { icon: "arrow-up", ring: "bg-up/10 text-up" },
  trim: { icon: "minus", ring: "bg-warn/10 text-warn" },
  exit: { icon: "logout", ring: "bg-warn/10 text-warn" },
  review: { icon: "check", ring: "bg-accent/10 text-accent" },
};

export default async function Journal({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const [entries, pms, ths] = await Promise.all([journal(), postmortems(), theses()]);
  const names = new Map(ths.map((t) => [t.id, t.companies ? `${t.companies.name} (${code(t.companies)})` : t.company_id]));
  const record = trackRecord(pms);
  return (
    <Page
      title="Journal"
      description={journalLine(entries.length, pms.length)}
      actions={
        <>
          <Chip title="Entries and post-mortems stay in your database">
            <Icon name="shield" className="size-3.5 text-up" strokeWidth={2.4} />
            Never sent to any LLM
          </Chip>
          {/* on the canvas, so the outline button: a secondary one reads like the chip beside it (PR 6 final review L5-4) */}
          <a href="#add-note" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "lg:hidden")}>
            <Icon name="plus" className="size-3.5" strokeWidth={2.4} />
            Add a note
          </a>
        </>
      }
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <div className="flex flex-wrap items-start gap-6">
        <Section
          title="Entries"
          id="entries"
          count={entries.length}
          description={entries.length > 0 ? "Newest first. Entries about a thesis are added on its page." : undefined}
          className="flex-[999_1_560px]"
        >
          {entries.length === 0 ? (
            <Empty>Your journal is empty. Write a first note: why something caught your eye, or what you&apos;d need to see.</Empty>
          ) : (
            <ul aria-label="Journal entries" className="flex flex-col">
              {byEntryDate(entries).map((e) => {
                const a = ACTION[e.action] ?? ACTION.note;
                return (
                  <li key={e.id} className="flex gap-3 border-t border-line py-3.5 first:border-t-0 first:pt-0">
                    <span aria-hidden="true" className={cn("grid size-9 shrink-0 place-items-center rounded-full", a.ring)}>
                      <Icon name={a.icon} strokeWidth={2.4} />
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[15px] font-semibold text-fg">{label(ACTION_LABEL, e.action)}</span>
                        {e.thesis_id ? (
                          <Link href={`/theses/${e.thesis_id}`} className="link-quiet text-[14px]">
                            {names.get(e.thesis_id) ?? "thesis"}
                          </Link>
                        ) : (
                          <span className="text-[14px] text-subtle">general</span>
                        )}
                        {e.portfolio_pct !== null ? (
                          <Chip size="sm">
                            <span>
                              <span className="num">{num(e.portfolio_pct)}%</span> of portfolio
                            </span>
                          </Chip>
                        ) : null}
                        <time dateTime={e.entry_date} className="num ml-auto text-[13px] whitespace-nowrap text-subtle">
                          {shortDate(e.entry_date, true)}
                        </time>
                      </div>
                      <p className="text-[14px] whitespace-pre-wrap break-words text-muted">{e.reason}</p>
                      {e.override_reason ? (
                        <p className="text-[13px] break-words text-warn">
                          <span className="font-semibold">Override:</span> {e.override_reason}
                        </p>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>

        <Section title="Add a note" id="add-note" description="A general note, not tied to a thesis." className="flex-[1_1_300px]">
          <form action={addNote} className="flex flex-col gap-3">
            <Field label="Date" htmlFor="n-date">
              <Input id="n-date" name="entry_date" type="date" defaultValue={localToday(new Date())} required />
            </Field>
            <Field label="Note" htmlFor="n-text">
              <Textarea id="n-text" name="reason" required className="min-h-32" placeholder="What you saw, and why it matters" />
            </Field>
            <div>
              <SubmitButton>Add note</SubmitButton>
            </div>
          </form>
        </Section>
      </div>

      <Section
        title="Post-mortems"
        id="postmortems"
        count={pms.length}
        description={
          pms.length > 0 ? (
            // the dots beside the record they draw, not alone at the sheet's far edge (PR 6 final review L5-8)
            <span className="inline-flex flex-wrap items-center gap-2">
              {recordLine(record)}
              <span
                role="img"
                aria-label={`${record.right} right, ${record.wrong} wrong, ${record.unclear} unclear`}
                className="inline-flex flex-wrap items-center gap-1"
              >
                {pms.map((p) => (
                  <Dot key={p.thesis_id} tone={p.thesis_right === null ? "muted" : p.thesis_right ? "up" : "down"} className="size-2.5" />
                ))}
              </span>
            </span>
          ) : undefined
        }
      >
        {pms.length === 0 ? (
          <Empty>No post-mortems yet. Closing a thesis asks for one: what happened, whether you were right, and the lesson.</Empty>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {pms.map((p) => {
              const note = signalsNote(p.signals_right);
              return (
                <li key={p.thesis_id} className="tile flex flex-col gap-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/theses/${p.thesis_id}`} className="link-quiet text-[15px] font-semibold">
                      {names.get(p.thesis_id) ?? "thesis"}
                    </Link>
                    <Chip variant={p.thesis_right === null ? "plain" : p.thesis_right ? "good" : "bad"} size="sm">
                      {p.thesis_right === null ? "Unclear" : p.thesis_right ? "Called right" : "Called wrong"}
                    </Chip>
                    <time dateTime={p.created_at} className="num ml-auto text-[13px] text-subtle">
                      {shortDate(p.created_at, true)}
                    </time>
                  </div>
                  <p className="text-[14px] whitespace-pre-wrap break-words text-fg">{p.what_happened}</p>
                  {p.lessons ? (
                    <div className="rounded-tile bg-panel px-3.5 py-2.5">
                      <p className="eyebrow">Lesson</p>
                      <p className="mt-0.5 text-[14px] whitespace-pre-wrap break-words text-fg">{p.lessons}</p>
                    </div>
                  ) : null}
                  {note ? (
                    <Disclosure summary="What the signals said">
                      <p className="whitespace-pre-wrap break-words">{note}</p>
                    </Disclosure>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </Page>
  );
}
