import { Markdown } from "@/components/markdown";
import { Empty, Page, Section, Stat } from "@/components/page";
import { SourceStatus } from "@/components/source-status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requireUser } from "@/lib/auth";
import { stripSection } from "@/lib/cards";
import { latestDigest, llmUse, overview, sourceHealth } from "@/lib/data";
import { providerLabel, sourceLabel } from "@/lib/labels";
import { lateSources } from "@/lib/staleness";

export const metadata = { title: "This week" };

// BRIEF §6 Home: the digest for this week; source health; LLM quota use; a stale-data banner (the layout's). The
// digest's own source-health and LLM sections are left out here: the tables below show the same, live.
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, sources, use, o] = await Promise.all([latestDigest(), sourceHealth(), llmUse(), overview()]);
  const now = new Date();
  const late = lateSources(sources, now).length;
  const body = digest ? stripSection(stripSection(digest.body_md, "Source health"), "LLM quota use") : "";
  return (
    <Page
      title="This week"
      description={o.week ? `Scores as of the week ending ${o.week}. Research only: no orders, no price alerts.` : "No week has been scored yet."}
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Candidates" value={o.buckets.candidate} hint={`${o.buckets.early} early · ${o.buckets.priced_in} priced-in`} href="/candidates" />
        <Stat label="Theses to review" value={o.review} hint="need a verdict" href="/theses" />
        <Stat label="Open positions" value={o.position} hint="theses in Position" href="/theses" />
        <Stat label="Stale sources" value={late} hint={late === 0 ? "all on time" : "past their SLA"} href="/#sources" />
      </div>
      <Section title={digest ? digest.title : "Weekly digest"} id="digest">
        {digest ? (
          <Markdown text={body} />
        ) : (
          <Empty>No digest yet. The weekly run writes one each Saturday, after it scores the universe.</Empty>
        )}
      </Section>
      <Section title="Source health" id="sources" description="When each data source last succeeded; late or stale ones show in the banner.">
        {sources.length === 0 ? (
          <Empty>No source has reported yet. The first weekly run fills this in.</Empty>
        ) : (
          <Table label="Source health">
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Last success</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s) => (
                <TableRow key={s.source}>
                  <TableCell className="font-medium">{sourceLabel(s.source)}</TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">
                    {s.last_success ? s.last_success.slice(0, 16).replace("T", " ") + "Z" : "never"}
                  </TableCell>
                  <TableCell>
                    <SourceStatus source={s} all={sources} now={now} />
                  </TableCell>
                  <TableCell className="max-w-md text-xs break-words text-gray-700">{s.last_error ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="LLM quota use" id="llm" description="Calls over the last 7 days, all on free tiers.">
        {use.length === 0 ? (
          <Empty>No LLM calls in the last 7 days.</Empty>
        ) : (
          <Table label="LLM quota use">
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
              {use.map((u) => (
                <TableRow key={u.provider}>
                  <TableCell className="font-medium">{providerLabel(u.provider)}</TableCell>
                  <TableCell num>{u.calls.toLocaleString("en-US")}</TableCell>
                  <TableCell num>{u.ok.toLocaleString("en-US")}</TableCell>
                  <TableCell num>{u.rateLimited.toLocaleString("en-US")}</TableCell>
                  <TableCell num>{u.tokensIn.toLocaleString("en-US")}</TableCell>
                  <TableCell num>{u.tokensOut.toLocaleString("en-US")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
    </Page>
  );
}
