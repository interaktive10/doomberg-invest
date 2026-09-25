import { Markdown } from "@/components/markdown";
import { Empty, Page, Section } from "@/components/page";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { latestDigest, llmUse, sourceHealth } from "@/lib/data";
import { staleSources } from "@/lib/staleness";

// BRIEF §6 Home: the digest for this week; source health; LLM quota use; a stale-data banner (the layout's).
export default async function Home() {
  const [digest, sources, use] = await Promise.all([latestDigest(), sourceHealth(), llmUse(7)]);
  const late = new Set(staleSources(sources, new Date()).map((s) => s.split(" ")[0]));
  return (
    <Page title="This week">
      <Section title={digest ? digest.title : "Weekly digest"} id="digest">
        {digest ? <Markdown text={digest.body_md} /> : <Empty>No digest yet. The weekly run writes one on Saturday.</Empty>}
      </Section>
      <Section title="Source health" id="sources">
        {sources.length === 0 ? (
          <Empty>No source has reported yet.</Empty>
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
                  <TableCell>{s.source}</TableCell>
                  <TableCell>{s.last_success ? s.last_success.slice(0, 16).replace("T", " ") + "Z" : "never"}</TableCell>
                  <TableCell>{s.stale ? "stale" : late.has(s.source) ? "late" : "ok"}</TableCell>
                  <TableCell className="max-w-md break-words">{s.last_error ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="LLM quota use (last 7 days)" id="llm">
        {use.length === 0 ? (
          <Empty>No LLM calls in the last 7 days.</Empty>
        ) : (
          <Table label="LLM quota use">
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Calls</TableHead>
                <TableHead>OK</TableHead>
                <TableHead>Rate-limited</TableHead>
                <TableHead>Tokens in</TableHead>
                <TableHead>Tokens out</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {use.map((u) => (
                <TableRow key={u.provider}>
                  <TableCell>{u.provider}</TableCell>
                  <TableCell>{u.calls}</TableCell>
                  <TableCell>{u.ok}</TableCell>
                  <TableCell>{u.rateLimited}</TableCell>
                  <TableCell>{u.tokensIn}</TableCell>
                  <TableCell>{u.tokensOut}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
    </Page>
  );
}
