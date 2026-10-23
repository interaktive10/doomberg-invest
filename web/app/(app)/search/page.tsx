import Link from "next/link";
import { redirect } from "next/navigation";
import { Chip, type ChipVariant } from "@/components/chip";
import { Icon } from "@/components/icons";
import { Empty, Flash, Note, Page, Section } from "@/components/page";
import { ScoreRing } from "@/components/score-ring";
import { TickerTile } from "@/components/ticker-tile";
import { scoresInLatestWeek, searchCompanies, type Bucket } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { BOARD_LABEL } from "@/lib/explain";
import { code } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { humanize } from "@/lib/labels";
import { exactMatch, parseSearch, rankHits, SEARCH_MAX, SEARCH_ROWS } from "@/lib/search";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Search" };

// The nav's company search (overhaul PR 5; BRIEF §6). lib/search.ts turns away anything but letters, digits, spaces
// and . & - (at most 40 characters) and escapes what it lets through; a code that matches exactly opens that Company
// page, otherwise up to 20 companies show with their market, bucket and Evidence in the latest scored week. Drawn in
// overhaul PR 6 as rows: the ticker tile, the name and code, the bucket as a chip (Candidate is "On the board", as on
// every screen) and Evidence as a ring.

const BUCKET_CHIP: Partial<Record<Bucket, ChipVariant>> = { candidate: "accent" };

export default async function Search({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const parsed = parseSearch(one(await searchParams, "q"));
  if (parsed.kind !== "ok") {
    return (
      <Page title="Search" description={`Find a company by its ticker or name: letters, digits, spaces and . & -, up to ${SEARCH_MAX} characters.`}>
        {parsed.kind === "bad" ? (
          <Flash error={parsed.message} />
        ) : (
          <Empty>
            <Icon name="search" className="mx-auto mb-2 block size-6 text-subtle" />
            Type a ticker or a name in the search box. Press <kbd className="rounded-md bg-hover px-1.5 py-0.5 text-[12px] font-medium text-fg">/</kbd> to
            jump to it.
          </Empty>
        )}
      </Page>
    );
  }
  const found = await searchCompanies(parsed.exact, parsed.contains, SEARCH_ROWS);
  const exact = exactMatch(found.exact, parsed.q);
  if (exact !== null) redirect(`/company/${exact}`);
  const hits = rankHits(found.hits, parsed.q);
  const { week, scores } = await scoresInLatestWeek(hits.map((h) => h.id));
  const many = hits.length === SEARCH_ROWS;
  return (
    <Page
      title="Search"
      description={
        hits.length === 0
          ? `Nothing matches "${parsed.q}".`
          : `${many ? `The first ${SEARCH_ROWS}` : hits.length} ${hits.length === 1 ? "company matches" : "companies match"} "${parsed.q}".`
      }
    >
      {/* the line above counts the hits; this one only says which week the chips and rings are of (PR 6 final review V4-11) */}
      <Section title="Results" id="results" description={week ? `As of the week ending ${shortDate(week, true)}.` : "No week has been scored yet."}>
        {hits.length === 0 ? (
          <Empty>No company matches. Try fewer letters, or the ticker.</Empty>
        ) : (
          <div className="flex flex-col gap-3">
            <ul aria-label="Search results" className="flex flex-col gap-2">
              {hits.map((h, i) => {
                const s = scores.get(h.id);
                const c = code(h);
                return (
                  <li
                    key={h.id}
                    className="tile rise relative flex items-center gap-3 p-3 transition-colors duration-150 hover:bg-hover"
                    style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                  >
                    <TickerTile ticker={c} className="hidden sm:grid" />
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <Link href={`/company/${h.id}`} className="link-quiet truncate text-[15px] font-semibold after:absolute after:inset-0 after:rounded-tile">
                        {h.name}
                      </Link>
                      <span className="num text-[13px] text-subtle">
                        {c} · {h.market === "us" ? "US" : "India"}
                      </span>
                    </div>
                    {s ? (
                      <Chip variant={BUCKET_CHIP[s.bucket] ?? "plain"} size="sm" className="shrink-0 font-semibold">
                        {BOARD_LABEL[s.bucket] ?? humanize(s.bucket)}
                      </Chip>
                    ) : (
                      <span className="shrink-0 text-[13px] text-subtle">not scored</span>
                    )}
                    <ScoreRing value={s ? Number(s.evidence) : null} kind="evidence" size={40} />
                  </li>
                );
              })}
            </ul>
            {many ? <Note>Only the first {SEARCH_ROWS} show. More letters, or the ticker, narrow it down.</Note> : null}
          </div>
        )}
      </Section>
    </Page>
  );
}
