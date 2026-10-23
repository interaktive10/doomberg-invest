import Link from "next/link";
import { Icon } from "@/components/icons";
import { CountPill, Empty, Page } from "@/components/page";
import { GROUP_HINT, GroupSection, ThesisRows } from "@/components/thesis-list";
import { buttonVariants } from "@/components/ui/button";
import { ensureReviews, thesisFigures, theses } from "@/lib/data";
import { thesesLine } from "@/lib/explain";
import { group, GROUP_LABEL, markMoved, type Group } from "@/lib/theses";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Theses" };

// BRIEF §6 Theses (overhaul PR 4): three groups, Needs you (cards to accept or dismiss, reviews to decide), Watching
// (theses and positions) and Closed (folded). Each row (components/thesis-list.tsx, overhaul PR 6): the ticker, what it
// asks of you, Evidence now as a ring and at the card's week, the kill criteria triggered and the next review. Open a
// row to decide, journal, review or close it. Home's To do is the Needs you group (overhaul PR 5).
export default async function Theses() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const first = await theses();
  const all = markMoved(first, await ensureReviews(first));
  const figures = await thesisFigures(all);
  const of = (g: Group) => all.filter((t) => group(t) === g);
  const [needs, watching, closed] = [of("needs"), of("watching"), of("closed")];
  return (
    <Page title="Theses" eyebrow="Research → thesis → position → closed" description={thesesLine(needs.length, watching.length)}>
      {all.length === 0 ? (
        <Empty
          action={
            // on the canvas: the outline button, as every empty state's (PR 6 final review L5-4)
            <Link href="/candidates" className={buttonVariants({ variant: "outline", size: "sm" })}>
              See the candidates
            </Link>
          }
        >
          No theses yet. Cards arrive from the weekly routine, or start one with Research on a company.
        </Empty>
      ) : (
        <>
          <GroupSection group="needs" list={needs} figures={figures} />
          <GroupSection group="watching" list={watching} figures={figures} />
          {closed.length > 0 ? (
            <details className="sheet group">
              <summary className="flex min-h-16 list-none items-center gap-2.5 rounded-sheet px-5 md:px-6 [&::-webkit-details-marker]:hidden">
                <span className="text-[20px] font-bold tracking-[-0.02em] text-fg">{GROUP_LABEL.closed}</span>
                <CountPill n={closed.length} className="bg-hover text-muted" />
                <span className="ml-auto hidden text-[14px] text-subtle sm:inline">{GROUP_HINT.closed}</span>
                <Icon name="chevron-down" className="ml-auto text-subtle transition-transform duration-200 group-open:rotate-180 sm:ml-0" />
              </summary>
              <div className="px-5 pb-5 md:px-6 md:pb-6">
                <ThesisRows list={closed} figures={figures} />
              </div>
            </details>
          ) : null}
        </>
      )}
    </Page>
  );
}
