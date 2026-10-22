import Link from "next/link";
import { Chip } from "@/components/chip";
import { Icon } from "@/components/icons";
import { Empty, Section } from "@/components/page";
import { ScoreRing } from "@/components/score-ring";
import { TickerTile } from "@/components/ticker-tile";
import { Badge } from "@/components/ui/badge";
import type { thesisFigures, Thesis } from "@/lib/data";
import { thesisAsk } from "@/lib/explain";
import { code } from "@/lib/format";
import { GROUP_LABEL, STATE_LABEL, type Group } from "@/lib/theses";

// The Theses screen's groups and rows (overhaul PR 4). Drawn as clean rows (overhaul PR 6): the ticker tile, the name
// and what the row asks of you, Evidence now as a ring (and what it was at the card), the kill criteria triggered, and
// the next review. Home's To do lists the same Needs you group with its own rows (app/(app)/page.tsx).

export const GROUP_HINT: Record<Group, string> = {
  needs: "Cards to accept or pass, and reviews waiting for your verdict.",
  watching: "Kill criteria checked every week; queued research waits for its card.",
  closed: "Closed with a post-mortem, or dismissed.",
};

const GROUP_EMPTY: Record<Group, string> = {
  needs: "Nothing needs you this week.",
  watching: "No thesis is being watched yet.",
  closed: "Nothing closed yet.",
};

export const STATE_BADGE = {
  research: "secondary",
  thesis: "default",
  position: "success",
  review: "warning",
  closed: "outline",
  dismissed: "outline",
} as const;

export type Figures = Awaited<ReturnType<typeof thesisFigures>>;

function rounded(v: number | null | undefined): number | null {
  return v === null || v === undefined || !Number.isFinite(v) ? null : Math.round(v);
}

/** The rows: each one a link to its thesis (the whole row is the target), read as the company's name and code. */
export function ThesisRows({ list, figures }: { list: readonly Thesis[]; figures: Figures }) {
  return (
    <ul className="flex flex-col gap-2">
      {list.map((t) => {
        const c = t.companies;
        const f = figures.get(t.id);
        const kills = f?.kills ?? [];
        const hit = kills.filter((k) => k === "triggered").length;
        const now = rounded(f?.now);
        const was = rounded(f?.atCard);
        return (
          <li key={t.id} className="tile relative flex items-center gap-3 p-3 transition-colors duration-150 hover:bg-hover">
            <TickerTile ticker={c ? code(c) : "?"} />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Link
                  href={`/theses/${t.id}`}
                  className="link-quiet text-[15px] font-semibold after:absolute after:inset-0 after:rounded-tile"
                >
                  {c ? c.name : t.company_id}
                  {c ? <span className="sr-only"> ({code(c)})</span> : null}
                </Link>
                <Badge variant={STATE_BADGE[t.state]}>{STATE_LABEL[t.state]}</Badge>
              </div>
              <p className="text-[13px] text-subtle">
                {thesisAsk(t)}
                {t.next_review ? (
                  <>
                    {" "}
                    · next review <span className="num">{t.next_review}</span>
                  </>
                ) : null}
                {kills.length > 0 ? (
                  <span className="sm:hidden">
                    {" "}
                    · kill criteria <span className="num">{hit}</span> of <span className="num">{kills.length}</span> triggered
                  </span>
                ) : null}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2.5">
              {kills.length > 0 ? (
                <Chip variant={hit > 0 ? "bad" : "good"} title="Kill criteria triggered" className="hidden sm:inline-flex">
                  <Icon name="shield" className="size-3.5" />
                  <span className="sr-only">Kill criteria: </span>
                  <span className="num">
                    {hit} of {kills.length}
                  </span>
                  <span className="sr-only"> triggered</span>
                </Chip>
              ) : null}
              <div className="flex flex-col items-center">
                <ScoreRing value={now} kind="evidence" size={44} label="Evidence now" />
                {was !== null && was !== now ? (
                  <span className="num text-[11px] leading-tight text-subtle">
                    <span className="sr-only">Evidence at the card </span>was {was}
                  </span>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** A group as a sheet: its name and count, one line on what it holds, then the rows (or a line saying there are
 * none). */
export function GroupSection({ group, list, figures }: { group: Group; list: readonly Thesis[]; figures: Figures }) {
  return (
    <Section title={GROUP_LABEL[group]} id={group} count={list.length} description={GROUP_HINT[group]}>
      {list.length === 0 ? <Empty>{GROUP_EMPTY[group]}</Empty> : <ThesisRows list={list} figures={figures} />}
    </Section>
  );
}
