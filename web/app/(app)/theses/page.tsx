import Link from "next/link";
import { Empty, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { ensureReviews, thesisFigures, theses, type Thesis } from "@/lib/data";
import { code, num } from "@/lib/format";
import { group, GROUP_LABEL, killTally, markMoved, STATE_LABEL, type Group } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Theses" };

// BRIEF §6 Theses (overhaul PR 4): three groups, Needs you (cards to accept or dismiss, reviews to decide), Watching
// (theses and positions) and Closed (folded). Each row: Evidence at the card's week and now, the kill criteria
// triggered, and the next review. Open a row to decide, journal, review or close it.
const HINT: Record<Group, string> = {
  needs: "cards to accept or dismiss, and reviews waiting for your verdict",
  watching: "accepted theses and positions; kill criteria are checked each week",
  closed: "closed with a post-mortem, or dismissed",
};

const STATE_BADGE = {
  research: "secondary",
  thesis: "default",
  position: "success",
  review: "warning",
  closed: "outline",
  dismissed: "outline",
} as const;

const COLUMNS = "lg:grid-cols-[minmax(0,1.6fr)_10rem_9rem_8rem]";

type Figures = Awaited<ReturnType<typeof thesisFigures>>;

function Rows({ list, figures }: { list: Thesis[]; figures: Figures }) {
  return (
    <ul className="flex flex-col">
      {list.map((t) => {
        const c = t.companies;
        const f = figures.get(t.id);
        return (
          <li key={t.id} className={cn("flex flex-col gap-2 border-t border-line py-3 first:border-t-0 first:pt-0 lg:grid lg:items-center lg:gap-x-4", COLUMNS)}>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Link href={`/theses/${t.id}`} className="link-quiet text-sm font-semibold">
                  {c ? `${c.name} (${code(c)})` : t.company_id}
                </Link>
                <Badge variant={STATE_BADGE[t.state]}>{STATE_LABEL[t.state]}</Badge>
              </div>
              <div className="num mt-0.5 text-xs text-muted">
                card week {t.created_week} · {t.author}
              </div>
            </div>
            <div className="text-[13px]">
              <span className="caps lg:sr-only">Evidence </span>
              <span className="num text-fg">{num(f?.atCard ?? null, 0)}</span>
              <span className="text-muted"> at the card → </span>
              <span className="num text-fg">{num(f?.now ?? null, 0)}</span>
              <span className="text-muted"> now</span>
            </div>
            <div className={cn("text-[13px]", (f?.kills ?? []).includes("triggered") ? "text-down" : "text-muted")}>
              <span className="caps lg:sr-only">Kill criteria </span>
              {killTally(f?.kills ?? [])}
            </div>
            <div className="text-[13px] text-muted">
              <span className="caps lg:sr-only">Next review </span>
              {t.next_review ? <span className="num text-fg">{t.next_review}</span> : "–"}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default async function Theses() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const first = await theses();
  const all = markMoved(first, await ensureReviews(first));
  const figures = await thesisFigures(all);
  const of = (g: Group) => all.filter((t) => group(t.state) === g);
  const closed = of("closed");
  const head = (
    <div aria-hidden="true" className={cn("caps mb-2 hidden border-b border-line pb-2 lg:grid lg:gap-x-4", COLUMNS)}>
      <span>Company</span>
      <span>Evidence</span>
      <span>Kill criteria</span>
      <span>Next review</span>
    </div>
  );
  return (
    <Page title="Theses" description="Research → Thesis → Position → Review → Closed. Open a row to decide, journal, review or close it.">
      {all.length === 0 ? <Empty>No theses yet. Cards arrive from the weekly routine, or start one with Research on Candidates.</Empty> : null}
      {(["needs", "watching"] as const).map((g) => (
        <Section
          key={g}
          title={`${GROUP_LABEL[g]} (${of(g).length})`}
          id={g}
          description={HINT[g]}
          className={g === "needs" && of(g).length > 0 ? "border-l-2 border-l-warn" : undefined}
        >
          {of(g).length === 0 ? (
            <Empty>{g === "needs" ? "Nothing needs you this week." : "No thesis is being watched."}</Empty>
          ) : (
            <>
              {head}
              <Rows list={of(g)} figures={figures} />
            </>
          )}
        </Section>
      ))}
      {closed.length > 0 ? (
        <details className="rounded-md border border-line bg-panel">
          <summary className="px-4 py-2.5 text-sm font-semibold text-fg">
            {GROUP_LABEL.closed} ({closed.length})
          </summary>
          <div className="border-t border-line p-4">
            <p className="mb-3 text-xs text-muted">{HINT.closed}</p>
            {head}
            <Rows list={closed} figures={figures} />
          </div>
        </details>
      ) : null}
    </Page>
  );
}
