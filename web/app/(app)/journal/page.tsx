import Link from "next/link";
import { Empty, Flash, Kpi, KpiRibbon, Page, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { journal, postmortems, theses } from "@/lib/data";
import { localToday } from "@/lib/discipline";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { ACTION_LABEL, label } from "@/lib/labels";
import { addNote } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Journal" };

// BRIEF §6 Journal: private entries and post-mortems. They live only in the database; the web app makes no LLM calls
// and the pipeline's privacy check refuses them (llm/privacy.py).
export default async function Journal({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const [entries, pms, ths] = await Promise.all([journal(), postmortems(), theses()]);
  const names = new Map(ths.map((t) => [t.id, t.companies ? `${t.companies.name} (${code(t.companies)})` : t.company_id]));
  const count = (action: string) => entries.filter((e) => e.action === action).length;
  return (
    <Page title="Journal" description="Private: entries and post-mortems stay in your database and are never sent to any LLM.">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <KpiRibbon>
        <Kpi label="Entries" value={entries.length} />
        <Kpi label="Positions started" value={count("start_position")} />
        <Kpi label="Exits" value={count("exit")} />
        <Kpi label="Thesis was right" value={pms.filter((p) => p.thesis_right === true).length} hint={`of ${pms.length} post-mortems`} />
      </KpiRibbon>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <Section title="Entries" id="entries" description="Newest first. Entries about a thesis are added on its page.">
          {entries.length === 0 ? (
            <Empty>No entries yet.</Empty>
          ) : (
            <Table label="Journal entries">
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Thesis</TableHead>
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
                    <TableCell className="min-w-40">
                      {e.thesis_id ? (
                        <Link href={`/theses/${e.thesis_id}`} className="link-quiet">
                          {names.get(e.thesis_id) ?? "thesis"}
                        </Link>
                      ) : (
                        <span className="text-muted">general</span>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{label(ACTION_LABEL, e.action)}</TableCell>
                    <TableCell num>{e.portfolio_pct === null ? "" : `${num(e.portfolio_pct)}%`}</TableCell>
                    <TableCell className="max-w-md min-w-48 break-words">{e.reason}</TableCell>
                    <TableCell className="max-w-xs break-words">{e.override_reason ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
        <Section title="Add a note" id="add-note" description="A general note, not tied to a thesis.">
          <form action={addNote} className="grid grid-cols-1 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="n-date">Date</Label>
              <Input id="n-date" name="entry_date" type="date" defaultValue={localToday(new Date())} required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="n-text">Note</Label>
              <Textarea id="n-text" name="reason" required className="min-h-28" />
            </div>
            <div>
              <SubmitButton>Add note</SubmitButton>
            </div>
          </form>
        </Section>
      </div>
      <Section title="Post-mortems" id="postmortems">
        {pms.length === 0 ? (
          <Empty>No post-mortems yet. Closing a thesis asks for one.</Empty>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {pms.map((p) => (
              <li key={p.thesis_id} className="rounded-sm border border-line bg-canvas p-3 text-[13px] sm:p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/theses/${p.thesis_id}`} className="link-quiet">
                    {names.get(p.thesis_id) ?? "thesis"}
                  </Link>
                  <span className="num text-xs text-muted">{p.created_at.slice(0, 10)}</span>
                  <Badge variant={p.thesis_right === null ? "secondary" : p.thesis_right ? "success" : "destructive"}>
                    thesis right: {p.thesis_right === null ? "unclear" : p.thesis_right ? "yes" : "no"}
                  </Badge>
                </div>
                <p className="mt-2 whitespace-pre-wrap">{p.what_happened}</p>
                <dl className="mt-2 grid gap-1">
                  <dt className="text-xs font-medium text-muted">Signals</dt>
                  <dd className="whitespace-pre-wrap">{String(p.signals_right?.note ?? "")}</dd>
                  <dt className="mt-1 text-xs font-medium text-muted">Lessons</dt>
                  <dd className="whitespace-pre-wrap">{p.lessons}</dd>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  );
}
