import Link from "next/link";
import type { ReactNode } from "react";
import { Empty, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import type { thesisFigures, Thesis } from "@/lib/data";
import { code, num } from "@/lib/format";
import { cardQueued, GROUP_LABEL, killTally, STATE_LABEL, type Group } from "@/lib/theses";
import { cn } from "@/lib/utils";

// The Theses screen's groups and rows (overhaul PR 4), shared with Home's To do (overhaul PR 5), which is the Needs you
// group: each row the company, its state, Evidence at the card's week and now, the kill criteria triggered and the next
// review.

export const GROUP_HINT: Record<Group, string> = {
  needs: "cards to accept or dismiss, and reviews waiting for your verdict",
  watching: "accepted theses and positions, whose kill criteria are checked each week, and research entries whose card is queued",
  closed: "closed with a post-mortem, or dismissed",
};

const GROUP_EMPTY: Record<Group, string> = {
  needs: "Nothing needs you this week.",
  watching: "No thesis is being watched.",
  closed: "Nothing closed yet.",
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

export type Figures = Awaited<ReturnType<typeof thesisFigures>>;

/** The column heads over the rows (on a wide screen; on a phone each cell names itself). */
export function ThesisHead() {
  return (
    <div aria-hidden="true" className={cn("caps mb-2 hidden border-b border-line pb-2 lg:grid lg:gap-x-4", COLUMNS)}>
      <span>Company</span>
      <span>Evidence</span>
      <span>Kill criteria</span>
      <span>Next review</span>
    </div>
  );
}

export function ThesisRows({ list, figures }: { list: readonly Thesis[]; figures: Figures }) {
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
                {cardQueued(t) ? <Badge variant="outline">card queued</Badge> : null}
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

/** A group as a panel: its name and count, its hint, then the rows (or a line saying there are none). Needs you is
 * marked on its left edge while it has rows. `title` and `id` rename it (Home's To do is Needs you). */
export function GroupSection({ group, list, figures, title, id }: { group: Group; list: readonly Thesis[]; figures: Figures; title?: ReactNode; id?: string }) {
  return (
    <Section
      title={<>{title ?? GROUP_LABEL[group]} ({list.length})</>}
      id={id ?? group}
      description={GROUP_HINT[group]}
      className={group === "needs" && list.length > 0 ? "border-l-2 border-l-warn" : undefined}
    >
      {list.length === 0 ? (
        <Empty>{GROUP_EMPTY[group]}</Empty>
      ) : (
        <>
          <ThesisHead />
          <ThesisRows list={list} figures={figures} />
        </>
      )}
    </Section>
  );
}
