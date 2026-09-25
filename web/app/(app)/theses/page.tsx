import Link from "next/link";
import { Empty, Page } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { ensureReviews, theses, type Thesis, type ThesisState } from "@/lib/data";
import { code } from "@/lib/format";
import { markMoved, STATE_LABEL } from "@/lib/theses";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Theses: a Kanban by state (§1.8 Research → Thesis → Position → Review → Closed; dismissed cards last).
const COLUMNS: ThesisState[] = ["research", "thesis", "position", "review", "closed"];

function CardLink({ t }: { t: Thesis }) {
  const c = t.companies;
  return (
    <li className="rounded-md border border-gray-300 bg-white p-2 text-sm">
      <Link href={`/theses/${t.id}`} className="font-medium">
        {c ? `${c.name} (${code(c)})` : t.company_id}
      </Link>
      <div className="mt-1 flex flex-wrap gap-1 text-xs text-gray-700">
        <span>week {t.created_week}</span>
        <Badge variant="secondary">{t.author}</Badge>
        {t.next_review ? <span>next review {t.next_review}</span> : null}
      </div>
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
    <Page title="Theses">
      {all.length === 0 ? <Empty>No theses yet. Cards arrive from the weekly routine, or start one from Candidates.</Empty> : null}
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        {COLUMNS.map((s) => (
          <section key={s} aria-labelledby={`col-${s}`} className="rounded-lg border border-gray-300 bg-gray-50 p-2">
            <h2 id={`col-${s}`} className="mb-2 font-semibold">
              {STATE_LABEL[s]} <span className="text-sm font-normal text-gray-700">({by(s).length})</span>
            </h2>
            {by(s).length === 0 ? (
              <p className="text-sm text-gray-700">None</p>
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
        <details className="mt-6">
          <summary className="cursor-pointer font-semibold">Dismissed ({dismissed.length})</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {dismissed.map((t) => (
              <CardLink key={t.id} t={t} />
            ))}
          </ul>
        </details>
      ) : null}
    </Page>
  );
}
