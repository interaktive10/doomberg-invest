import Link from "next/link";
import { Empty, Flash, Page, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { journal, postmortems, theses } from "@/lib/data";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { addNote } from "./actions";

// BRIEF §6 Journal: private entries and post-mortems. They live only in the database; the web app makes no LLM calls
// and the pipeline's privacy check refuses them (llm/privacy.py).
export default async function Journal({ searchParams }: { searchParams: Promise<Query> }) {
  const q = await searchParams;
  const [entries, pms, ths] = await Promise.all([journal(), postmortems(), theses()]);
  const names = new Map(ths.map((t) => [t.id, t.companies ? `${t.companies.name} (${code(t.companies)})` : t.company_id]));
  return (
    <Page title="Journal">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <p className="text-sm text-gray-700">Private: never sent to any LLM.</p>
      <Section title="Entries" id="entries">
        {entries.length === 0 ? (
          <Empty>No entries yet.</Empty>
        ) : (
          <Table label="Journal entries">
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Thesis</TableHead>
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
                  <TableCell>{e.thesis_id ? <Link href={`/theses/${e.thesis_id}`}>{names.get(e.thesis_id) ?? "thesis"}</Link> : "general"}</TableCell>
                  <TableCell>{e.action}</TableCell>
                  <TableCell>{e.portfolio_pct === null ? "" : `${num(e.portfolio_pct)}%`}</TableCell>
                  <TableCell className="max-w-md break-words">{e.reason}</TableCell>
                  <TableCell className="max-w-xs break-words">{e.override_reason ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <form action={addNote} className="mt-4 grid gap-3 rounded-md border border-gray-300 p-3 md:max-w-xl">
          <h3 className="font-semibold">Add a note</h3>
          <Label htmlFor="n-date">Date</Label>
          <Input id="n-date" name="entry_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required />
          <Label htmlFor="n-text">Note</Label>
          <Textarea id="n-text" name="reason" required />
          <div>
            <Button type="submit">Add note</Button>
          </div>
        </form>
      </Section>
      <Section title="Post-mortems" id="postmortems">
        {pms.length === 0 ? (
          <Empty>No post-mortems yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-3">
            {pms.map((p) => (
              <li key={p.thesis_id} className="rounded-md border border-gray-300 p-3 text-sm">
                <Link href={`/theses/${p.thesis_id}`} className="font-medium">
                  {names.get(p.thesis_id) ?? "thesis"}
                </Link>{" "}
                · {p.created_at.slice(0, 10)} · thesis right: {p.thesis_right === null ? "unclear" : p.thesis_right ? "yes" : "no"}
                <p className="mt-1 whitespace-pre-wrap">{p.what_happened}</p>
                <p className="mt-1 whitespace-pre-wrap">Signals: {String(p.signals_right?.note ?? "")}</p>
                <p className="mt-1 whitespace-pre-wrap">Lessons: {p.lessons}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  );
}
