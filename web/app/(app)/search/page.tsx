import Link from "next/link";
import { redirect } from "next/navigation";
import { Empty, Flash, Page, Section } from "@/components/page";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { scoresInLatestWeek, searchCompanies } from "@/lib/data";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { BUCKET_LABEL, label } from "@/lib/labels";
import { exactMatch, parseSearch, rankHits, SEARCH_MAX, SEARCH_ROWS } from "@/lib/search";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Search" };

// The nav's company search (overhaul PR 5; BRIEF §6). lib/search.ts turns away anything but letters, digits, spaces
// and . & - (at most 40 characters) and escapes what it lets through; a code that matches exactly opens that Company
// page, otherwise up to 20 companies show with their market, bucket and Evidence in the latest scored week.
export default async function Search({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const parsed = parseSearch(one(await searchParams, "q"));
  if (parsed.kind !== "ok") {
    return (
      <Page title="Search" description={`Find a company by its ticker or name: letters, digits, spaces and . & -, up to ${SEARCH_MAX} characters.`}>
        {parsed.kind === "bad" ? <Flash error={parsed.message} /> : <Empty>Type a ticker or a name in the search box (press / to jump to it).</Empty>}
      </Page>
    );
  }
  const found = await searchCompanies(parsed.exact, parsed.contains, SEARCH_ROWS);
  const exact = exactMatch(found.exact, parsed.q);
  if (exact !== null) redirect(`/company/${exact}`);
  const hits = rankHits(found.hits, parsed.q);
  const { week, scores } = await scoresInLatestWeek(hits.map((h) => h.id));
  return (
    <Page title="Search" description={`Companies whose ticker or name contains "${parsed.q}".`}>
      <Section
        title={`${hits.length === SEARCH_ROWS ? `The first ${SEARCH_ROWS}` : hits.length} ${hits.length === 1 ? "company" : "companies"}`}
        id="results"
        description={week ? `Bucket and Evidence in the week ending ${week}.` : "No week has been scored yet."}
      >
        {hits.length === 0 ? (
          <Empty>No company matches. Try fewer letters, or the ticker.</Empty>
        ) : (
          <Table label="Search results">
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Code</TableHead>
                <TableHead>Market</TableHead>
                <TableHead>Bucket</TableHead>
                <TableHead num>Evidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {hits.map((h) => {
                const s = scores.get(h.id);
                return (
                  <TableRow key={h.id}>
                    <TableCell>
                      <Link href={`/company/${h.id}`} className="link-quiet">
                        {h.name}
                      </Link>
                    </TableCell>
                    <TableCell className="num">{code(h)}</TableCell>
                    <TableCell>{h.market === "us" ? "US" : "India"}</TableCell>
                    <TableCell>{s ? label(BUCKET_LABEL, s.bucket) : <span className="text-muted">not scored</span>}</TableCell>
                    <TableCell num>{s ? num(s.evidence, 0) : "–"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Section>
    </Page>
  );
}
