import { Empty, Page } from "@/components/page";
import { GROUP_HINT, GroupSection, ThesisHead, ThesisRows } from "@/components/thesis-list";
import { ensureReviews, thesisFigures, theses } from "@/lib/data";
import { group, GROUP_LABEL, markMoved, type Group } from "@/lib/theses";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Theses" };

// BRIEF §6 Theses (overhaul PR 4): three groups, Needs you (cards to accept or dismiss, reviews to decide), Watching
// (theses and positions) and Closed (folded). Each row: Evidence at the card's week and now, the kill criteria
// triggered, and the next review. Open a row to decide, journal, review or close it. Home's To do is the Needs you
// group (components/thesis-list.tsx, overhaul PR 5).
export default async function Theses() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const first = await theses();
  const all = markMoved(first, await ensureReviews(first));
  const figures = await thesisFigures(all);
  const of = (g: Group) => all.filter((t) => group(t) === g);
  const closed = of("closed");
  return (
    <Page title="Theses" description="Research → Thesis → Position → Review → Closed. Open a row to decide, journal, review or close it.">
      {all.length === 0 ? <Empty>No theses yet. Cards arrive from the weekly routine, or start one with Research on a company.</Empty> : null}
      {(["needs", "watching"] as const).map((g) => (
        <GroupSection key={g} group={g} list={of(g)} figures={figures} />
      ))}
      {closed.length > 0 ? (
        <details className="rounded-md border border-line bg-panel">
          <summary className="px-4 py-2.5 text-sm font-semibold text-fg">
            {GROUP_LABEL.closed} ({closed.length})
          </summary>
          <div className="border-t border-line p-4">
            <p className="mb-3 text-xs text-muted">{GROUP_HINT.closed}</p>
            <ThesisHead />
            <ThesisRows list={closed} figures={figures} />
          </div>
        </details>
      ) : null}
    </Page>
  );
}
