import Link from "next/link";
import { Empty, Kpi, KpiRibbon, Page } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { ensureReviews, theses, type Thesis, type ThesisState } from "@/lib/data";
import { code } from "@/lib/format";
import { markMoved, STATE_LABEL } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Theses" };

// BRIEF §6 Theses: a Kanban by state (§1.8 Research → Thesis → Position → Review → Closed; dismissed cards last).
const COLUMNS: ThesisState[] = ["research", "thesis", "position", "review", "closed"];

const HINT: Record<ThesisState, string> = {
  research: "cards to read and decide on",
  thesis: "accepted; watching the kill criteria",
  position: "a position is recorded in the journal",
  review: "a filing or a kill criterion needs a verdict",
  closed: "closed with a post-mortem",
  dismissed: "",
};

// Each column's top rule: accent for a thesis, up for a position, warn for a review.
const ACCENT: Record<ThesisState, string> = {
  research: "border-t-subtle",
  thesis: "border-t-accent",
  position: "border-t-up",
  review: "border-t-warn",
  closed: "border-t-muted",
  dismissed: "border-t-line-strong",
};

function CardLink({ t }: { t: Thesis }) {
  const c = t.companies;
  return (
    <li className="rounded-sm border border-line bg-raised p-2.5 text-[13px] transition-colors hover:border-edge">
      <Link href={`/theses/${t.id}`} className="link-quiet">
        {c ? `${c.name} (${code(c)})` : t.company_id}
      </Link>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="num text-xs text-muted">week {t.created_week}</span>
        <Badge variant="secondary">{t.author}</Badge>
      </div>
      {t.next_review ? <div className="num mt-1 text-xs text-muted">next review {t.next_review}</div> : null}
    </li>
  );
}

export default async function Theses() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const first = await theses();
  const all = markMoved(first, await ensureReviews(first));
  const by = (s: ThesisState) => all.filter((t) => t.state === s);
  const dismissed = by("dismissed");
  const live = all.filter((t) => t.state !== "closed" && t.state !== "dismissed" && t.next_review !== null);
  const due = live.reduce<Thesis | undefined>((soonest, t) => (soonest === undefined || (t.next_review ?? "") < (soonest.next_review ?? "") ? t : soonest), undefined);
  const open = by("thesis").length + by("position").length + by("review").length;
  return (
    <Page title="Theses" description="Research → Thesis → Position → Review → Closed. Open a card to decide, journal, or review it.">
      <KpiRibbon>
        <Kpi label="Open theses" value={open} />
        <Kpi label="Need a verdict" value={by("review").length} tone={by("review").length > 0 ? "warn" : undefined} />
        <Kpi label="Positions" value={by("position").length} tone={by("position").length > 0 ? "up" : undefined} />
        <Kpi label="Earliest review" value={due?.next_review ?? "–"} hint={due?.companies ? code(due.companies) : undefined} />
        <Kpi label="Closed" value={by("closed").length} />
      </KpiRibbon>
      {all.length === 0 ? <Empty>No theses yet. Cards arrive from the weekly routine, or start one with Research on Candidates.</Empty> : null}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {COLUMNS.map((s) => (
          <section
            key={s}
            aria-labelledby={`col-${s}`}
            className={cn("flex min-w-0 flex-col rounded-md border border-t-2 border-line bg-panel", ACCENT[s])}
          >
            <h2 id={`col-${s}`} className="flex items-center justify-between px-3 pt-3 text-sm font-semibold text-fg">
              {STATE_LABEL[s]}
              <span className="rounded-sm bg-raised px-1.5 font-mono text-xs text-muted ring-1 ring-line-strong ring-inset">{by(s).length}</span>
            </h2>
            <p className="mx-3 mt-0.5 mb-3 text-xs text-muted">{HINT[s]}</p>
            {by(s).length === 0 ? (
              <p className="mx-3 mb-3 rounded-sm border border-dashed border-line-strong px-3 py-4 text-center text-xs text-muted">None</p>
            ) : (
              <ul className="flex flex-col gap-2 px-3 pb-3">
                {by(s).map((t) => (
                  <CardLink key={t.id} t={t} />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
      {dismissed.length > 0 ? (
        <details className="rounded-md border border-line bg-panel p-4">
          <summary className="text-sm font-semibold text-fg">Dismissed ({dismissed.length})</summary>
          <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {dismissed.map((t) => (
              <CardLink key={t.id} t={t} />
            ))}
          </ul>
        </details>
      ) : null}
    </Page>
  );
}
