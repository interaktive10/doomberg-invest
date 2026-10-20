import { Empty, Flash, Page, Section } from "@/components/page";
import { SourceStatus } from "@/components/source-status";
import { SubmitButton } from "@/components/submit-button";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { llmUse, setting, sourceHealth } from "@/lib/data";
import { one, type Query } from "@/lib/forms";
import { providerLabel, sourceLabel } from "@/lib/labels";
import { watched } from "@/lib/staleness";
import { saveDiscipline } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Settings" };

// BRIEF §6 Settings (overhaul PR 4): the health of the US sources the pipeline reads, the §11.9 discipline rule
// (configurable here) and the last 7 days of LLM calls per provider with the rate-limited ones. The config files
// (universes, quotas, weights) live in the repository and change through pull requests; the weights in use are on
// the Signal Lab page.
export default async function Settings({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const [all, weeks, llm] = await Promise.all([
    sourceHealth(),
    setting<number | string>("position_min_thesis_weeks", 4),
    llmUse(),
  ]);
  const sources = watched(all);
  const now = new Date();
  return (
    <Page title="Settings" description="Most settings live in the repository's config files and change through pull requests.">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12 xl:items-start">
        <Section title="Sources" id="sources" description="The US sources the pipeline reads, against their §2.7 SLA." className="xl:col-span-7">
          {sources.length === 0 ? (
            <Empty>No source has reported yet.</Empty>
          ) : (
            <Table label="Sources">
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Last success</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((s) => (
                  <TableRow key={s.source}>
                    <TableCell className="font-medium">{sourceLabel(s.source)}</TableCell>
                    <TableCell className="num whitespace-nowrap">
                      {s.last_success ? s.last_success.slice(0, 16).replace("T", " ") + "Z" : "never"}
                    </TableCell>
                    <TableCell>
                      <SourceStatus source={s} all={all} now={now} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
        <Section title="Discipline" id="discipline" description="An earlier start-position entry needs a written override reason (§11.9)." className="xl:col-span-5">
          <form action={saveDiscipline} className="flex flex-col gap-1.5">
            <Label htmlFor="weeks">Weeks a thesis must be old before a start-position entry</Label>
            <div className="flex items-center gap-2">
              <Input id="weeks" name="weeks" type="number" min="0" max="104" step="1" defaultValue={String(weeks)} className="w-28" required />
              <SubmitButton>Save</SubmitButton>
            </div>
          </form>
        </Section>
        <Section
          title="LLM calls, last 7 days"
          id="llm"
          description="Per provider, counted in the database; rate-limited calls are the free tiers' limits answering."
          className="xl:col-span-12"
        >
          {llm.length === 0 ? (
            <Empty>No LLM calls in the last 7 days.</Empty>
          ) : (
            <Table label="LLM calls, last 7 days">
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead num>Calls</TableHead>
                  <TableHead num>OK</TableHead>
                  <TableHead num>Rate-limited</TableHead>
                  <TableHead num>Tokens in</TableHead>
                  <TableHead num>Tokens out</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {llm.map((u) => (
                  <TableRow key={u.provider}>
                    <TableCell className="font-medium">{providerLabel(u.provider)}</TableCell>
                    <TableCell num>{u.calls.toLocaleString("en-US")}</TableCell>
                    <TableCell num>{u.ok.toLocaleString("en-US")}</TableCell>
                    <TableCell num className={u.rateLimited > 0 ? "text-warn" : undefined}>
                      {u.rateLimited.toLocaleString("en-US")}
                    </TableCell>
                    <TableCell num>{u.tokensIn.toLocaleString("en-US")}</TableCell>
                    <TableCell num>{u.tokensOut.toLocaleString("en-US")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      </div>
    </Page>
  );
}
