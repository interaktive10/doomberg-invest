import Link from "next/link";
import { Empty, Page } from "@/components/page";
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

const ACCENT: Record<ThesisState, string> = {
  research: "border-t-gray-400",
  thesis: "border-t-blue-700",
  position: "border-t-green-700",
  review: "border-t-amber-600",
  closed: "border-t-gray-800",
  dismissed: "border-t-gray-300",
};

function CardLink({ t }: { t: Thesis }) {
  const c = t.companies;
  return (
    <li className="rounded-lg border border-gray-200 bg-white p-3 text-sm shadow-sm transition-colors hover:border-blue-300">
      <Link href={`/theses/${t.id}`} className="link-quiet">
        {c ? `${c.name} (${code(c)})` : t.company_id}
      </Link>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-gray-700">
        <span className="tabular-nums">week {t.created_week}</span>
        <Badge variant="secondary">{t.author}</Badge>
      </div>
      {t.next_review ? <div className="mt-1 text-xs text-gray-700 tabular-nums">next review {t.next_review}</div> : null}
    </li>
  );
}

export default async function Theses() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const first = await theses();
  const all = markMoved(first, await ensureReviews(first));
  const by = (s: ThesisState) => all.filter((t) => t.state === s);
  const dismissed = by("dismissed");
  return (
    <Page title="Theses" description="Research → Thesis → Position → Review → Closed. Open a card to decide, journal, or review it.">
      {all.length === 0 ? <Empty>No theses yet. Cards arrive from the weekly routine, or start one with Research on Candidates.</Empty> : null}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {COLUMNS.map((s) => (
          <section
            key={s}
            aria-labelledby={`col-${s}`}
            className={cn("flex flex-col rounded-xl border border-t-4 border-gray-200 bg-gray-100/70 p-3", ACCENT[s])}
          >
            <h2 id={`col-${s}`} className="flex items-center gap-2 font-semibold">
              {STATE_LABEL[s]}
              <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-gray-700 ring-1 ring-gray-200">{by(s).length}</span>
            </h2>
            <p className="mt-0.5 mb-3 text-xs text-gray-700">{HINT[s]}</p>
            {by(s).length === 0 ? (
              <p className="rounded-lg border border-dashed border-gray-300 px-3 py-4 text-center text-xs text-gray-700">None</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {by(s).map((t) => (
                  <CardLink key={t.id} t={t} />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
      {dismissed.length > 0 ? (
        <details className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <summary className="font-semibold">Dismissed ({dismissed.length})</summary>
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
