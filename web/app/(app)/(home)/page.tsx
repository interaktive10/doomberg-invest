import Link from "next/link";
import { LinkPending } from "@/components/link-pending";
import { Callout } from "@/components/callout";
import { Chip, DotRow } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Icon, type IconName } from "@/components/icons";
import { Markdown } from "@/components/markdown";
import { Empty, Freshness, Page, Section } from "@/components/page";
import { ScoreRing } from "@/components/score-ring";
import { TickerTile } from "@/components/ticker-tile";
import { buttonVariants } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { byMarket, MARKET_LABEL, stillDismissed } from "@/lib/candidates";
import { dismissals, ensureReviews, latestDigest, latestReport, screen, sourceHealth, theses, thesisFigures, type ScreenerRow, type Thesis } from "@/lib/data";
import { dayDate, weekEyebrow } from "@/lib/dates";
import { code } from "@/lib/format";
import {
  boardWhy,
  boardWhyAll,
  changeItems,
  comingUp,
  funnelTotals,
  headline,
  homeSections,
  lateLine,
  parseFunnel,
  shownDelta,
  todoAsk,
  todoMinutes,
  type ChangeDir,
  type ChangeItem,
  type Upcoming,
} from "@/lib/home";
import { familyTone } from "@/lib/palette";
import { lateSources } from "@/lib/staleness";
import { group, markMoved } from "@/lib/theses";
import { nextRunDate } from "@/lib/schedule";
import { cn } from "@/lib/utils";
import { signedPct, topWinner, type WinnersReport } from "@/lib/winners";

export const metadata = { title: "This week" };

// BRIEF §6 Home, drawn as the overhaul PR 6 mock: the week and one line that leads with the answer; the funnel as four
// numbers with bars and its one insight (the digest's This week, the line itself under Details); To do (the Theses
// screen's Needs you group, read live) as rows with the decision each needs; What changed (the digest's section) as a
// feed with a direction and the Evidence move per line, then Coming up (the live cards' next filings); On the board
// (the Candidate bucket of the latest scored week, less the names a dismissal still hides, as Candidates counts them)
// with Evidence rings, per market, and a line counting the names a dismissal hides; Watch (each market's few
// one-family names at full strength, docs/SPEC_ISSUES.md 56) the same way; Data health with a dot per source the pipeline
// reads, and the stale-data line when one is late (Home alone has it). The digest's own words, codes and all, stay in
// each row's tooltip and the funnel's Details, so Home and the issue still read the same. Before the first weekly run
// (no digest) the headline says so once: no funnel, and no buttons to screens that are empty too (PR 6 final review).
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, sources, first, ranked, watching, winners] = await Promise.all([
    latestDigest(),
    sourceHealth(),
    theses(),
    screen({ buckets: ["candidate"], limit: 500 }),
    screen({ buckets: ["watch"], limit: 100 }),
    latestReport<WinnersReport>("winners"),
  ]);
  const week = ranked[0]?.week_end;
  const held = week ? await dismissals(ranked.map((r) => r.company_id), week) : new Map<string, never>();
  const hidden = stillDismissed(ranked, held);
  const board = ranked.filter((r) => !hidden.has(r.company_id));
  const all = markMoved(first, await ensureReviews(first)); // as the Theses screen does, so both list the same
  const needs = all.filter((t) => group(t) === "needs");
  const figures = await thesisFigures(needs);
  const { funnel, changed, legacy } = homeSections(digest?.body_md ?? "");
  const totals = funnelTotals(parseFunnel(funnel));
  const items = changeItems(changed);
  const now = new Date();
  const kills = new Map([...figures].map(([id, f]) => [id, f.kills.length]));
  const upcoming = comingUp(all, now.toISOString().slice(0, 10), kills);
  const late = lateSources(sources, now).length;
  const lateText = lateLine(sources, now);
  const winner = topWinner(winners?.body ?? null);
  return (
    <Page
      eyebrow={digest ? weekEyebrow(digest.week_end) : undefined}
      title="This week"
      description={headline({ digest: digest !== null, totals, funnel, legacy })}
      actions={digest ? <AsOf week={digest.week_end} late={late} /> : undefined}
      freshness={digest ? <Freshness items={[{ label: "Scores as of", date: digest.week_end }]} next={nextRunDate("weekly", new Date())} /> : null}
    >
      <nav aria-label="Shortcuts" className="grid grid-cols-3 gap-3 md:gap-4">
        <Shortcut href="/candidates" icon="tag" tone="value" value={board.length} label="undervalued" sub={watching.length > 0 ? `+${watching.length} on Watch` : "on the board"} i={0} />
        <Shortcut href="/theses" icon="bookmark" tone="list" value={needs.length} label="to do" sub={needs.length > 0 ? `about ${todoMinutes(needs.length)} min` : "all clear"} i={1} />
        <Shortcut
          href="/winners"
          icon="trophy"
          tone="winner"
          value={winner ? signedPct(winner.ret) : "–"}
          valueClass={winner ? (winner.ret >= 0 ? "text-up" : "text-down") : undefined}
          label={winner ? `${winner.code ?? winner.name}` : "winners"}
          sub={winner ? winner.label : "computed Saturday"}
          i={2}
        />
      </nav>
      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
          {needs.length > 0 ? (
            <Section id="todo" title="To do" count={needs.length}>
              <ul className="flex flex-col gap-2">
                {needs.map((t) => (
                  <TodoRow key={t.id} t={t} f={figures.get(t.id)} />
                ))}
              </ul>
            </Section>
          ) : null}
          <Section id="changed" title="What changed">
            {items.length > 0 ? (
              <Feed items={items} />
            ) : changed ? (
              <p className="text-[15px] text-muted">{changed}</p>
            ) : legacy ? (
              <Markdown text={legacy} />
            ) : (
              <Empty>{WAITING}</Empty>
            )}
            <ComingUp list={upcoming} />
          </Section>
        </div>
        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">
          <Section
            id="board"
            title="On the board"
            actions={
              board.length > 0 ? (
                <Link href="/candidates" className="inline-flex min-h-11 items-center text-[14px] font-medium no-underline md:min-h-0">
                  All {board.length}
                  <span className="sr-only"> on the board</span>
                </Link>
              ) : undefined
            }
          >
            <Board rows={board} hidden={hidden.size} waiting={digest === null} />
          </Section>
          {lateText ? (
            <Section
              id="health"
              title="Data health"
              quiet
              actions={
                <Link href="/settings#sources" className="inline-flex min-h-11 items-center text-[14px] font-medium no-underline md:min-h-0">
                  Sources<span className="sr-only"> in Settings</span>
                </Link>
              }
            >
              <Callout tone="warn">{lateText}</Callout>
            </Section>
          ) : null}
        </div>
      </div>
    </Page>
  );
}

const SHORTCUT_TONE = {
  value: { tile: "bg-tint-sage", icon: "text-up" },
  list: { tile: "bg-tint-sky", icon: "text-accent" },
  winner: { tile: "bg-tint-sand", icon: "text-warn" },
} as const;

/** One of Home's three doors: a big figure, what it counts, one small line. */
function Shortcut({ href, icon, tone, value, label, sub, i, valueClass }: { href: string; icon: IconName; tone: keyof typeof SHORTCUT_TONE; value: number | string; label: string; sub: string; i: number; valueClass?: string }) {
  const t = SHORTCUT_TONE[tone];
  return (
    <Link
      href={href}
      style={{ "--i": i } as React.CSSProperties}
      className={cn("rise press flex min-w-0 flex-col gap-1 rounded-sheet p-3.5 text-fg no-underline transition-transform duration-150 hover:-translate-y-0.5 hover:text-fg md:p-5", t.tile)}
    >
      <Icon name={icon} className={cn("size-5 md:size-6", t.icon)} strokeWidth={2.2} />
      <span className={cn("num mt-1 truncate text-[24px] leading-none font-bold tracking-[-0.03em] md:text-[34px]", valueClass)}>{value}</span>
      <span className="truncate text-[13px] font-semibold md:text-[15px]">{label}</span>
      <span className="hidden truncate text-[12px] text-muted sm:block md:text-[13px]">{sub}</span>
      <LinkPending />
    </Link>
  );
}

/** The empty line of a section the weekly digest fills, before its first run: the headline already says why. */
const WAITING = "Waiting for Saturday's run.";

/** "Data as of Fri, Sep 18": amber, and a link down to Data health, while a source is late. */
function AsOf({ week, late }: { week: string; late: number }) {
  const text = `Data as of ${dayDate(week)}`;
  if (late === 0) return <Chip dot="up">{text}</Chip>;
  return (
    <Link href="#health" className="inline-flex min-h-11 items-center rounded-full no-underline md:min-h-0">
      <Chip variant="warn" dot="warn">
        {text} · {late} {late === 1 ? "source" : "sources"} late
      </Chip>
    </Link>
  );
}

type Figure = { atCard: number | null; now: number | null; kills: string[] };

/** A card to accept or pass, or a review to give a verdict on: the whole row opens it. */
function TodoRow({ t, f }: { t: Thesis; f: Figure | undefined }) {
  const c = t.companies;
  const ticker = c ? code(c) : "";
  const { ask, short, action, alert } = todoAsk(t.state, f);
  return (
    <li>
      <Link
        href={`/theses/${t.id}`}
        className="tile flex min-h-15 items-center gap-3.5 p-3 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
      >
        <TickerTile ticker={ticker || "?"} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[15px] font-semibold">
            {c?.name ?? t.company_id}
            {ticker ? <span className="sr-only"> ({ticker})</span> : null}
          </span>
          {/* a phone's one short line (the phone mock), the full ask from sm up */}
          <span className={cn("text-[13px]", alert ? "font-medium text-down" : "text-muted")}>
            <span className="sm:hidden">{short}</span>
            <span className="hidden sm:inline">{ask}</span>
          </span>
        </span>
        <span className={cn(buttonVariants({ size: "sm" }), "hidden sm:inline-flex")}>{action}</span>
        <Icon name="chevron-right" className="text-subtle sm:hidden" />
        <LinkPending />
      </Link>
    </li>
  );
}

const GLYPH: Record<ChangeDir, { icon: IconName; ring: string; text: string }> = {
  up: { icon: "arrow-up", ring: "bg-up/10 text-up", text: "text-up" },
  down: { icon: "arrow-down", ring: "bg-warn/10 text-warn", text: "text-warn" },
  flat: { icon: "minus", ring: "bg-hover text-muted", text: "text-muted" },
  bad: { icon: "alert", ring: "bg-down/10 text-down", text: "text-down" },
  news: { icon: "doc", ring: "bg-accent/10 text-accent", text: "text-accent" },
};

const SHOWN = 5;

/** What changed as a feed: the first eight lines, the rest one tap away. */
function Feed({ items }: { items: ChangeItem[] }) {
  const rest = items.slice(SHOWN);
  return (
    <>
      <ul className="flex flex-col">
        {items.slice(0, SHOWN).map((c, i) => (
          <ChangeRow key={i} c={c} />
        ))}
      </ul>
      {rest.length > 0 ? (
        <Disclosure summary={`${rest.length} more`} className="mt-1">
          <ul className="flex flex-col">
            {rest.map((c, i) => (
              <ChangeRow key={i} c={c} />
            ))}
          </ul>
        </Disclosure>
      ) : null}
    </>
  );
}

/** One change: a glyph for its direction, the company and what happened, why in plain words, and the Evidence move on
 * the right, rounded as the rings round it (lib/home.ts shownDelta). The digest's line, codes and all, is the row's
 * tooltip. */
function ChangeRow({ c }: { c: ChangeItem }) {
  const g = GLYPH[c.dir];
  return (
    <li className="flex gap-3.5 border-t border-line py-3 first:border-t-0 first:pt-1" title={`${c.code} ${c.raw}`}>
      <span aria-hidden="true" className={cn("grid size-9 shrink-0 place-items-center rounded-full", g.ring)}>
        <Icon name={g.icon} strokeWidth={2.4} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-[15px] font-semibold text-fg">
          <Link href={c.href} className="link-quiet font-bold">
            {c.code}
          </Link>{" "}
          {c.title}
          {c.families.length > 0 ? <DotRow tones={c.families.map(familyTone)} className="ml-2 align-middle" /> : null}
        </p>
        {c.why ? <p className="text-[14px] text-muted">{c.why}</p> : null}
      </div>
      {c.delta ? (
        <p className={cn("num shrink-0 pt-0.5 text-[14px] font-semibold", g.text)}>
          {c.delta.label === "Evidence" ? <span className="sr-only">Evidence </span> : "Gap "}
          {shownDelta(c.delta.value)}
        </p>
      ) : null}
    </li>
  );
}

/** The live cards' next filings, as chips; left out when there are none. */
function ComingUp({ list }: { list: Upcoming[] }) {
  if (list.length === 0) return null;
  return (
    <div className="mt-5 flex flex-col gap-2.5">
      <h3 className="eyebrow">Coming up</h3>
      <ul className="flex flex-wrap gap-2">
        {list.map((u) => (
          <li key={u.id}>
            <Chip>
              <Icon name="calendar" className="size-3.5 text-subtle" />
              <strong className="font-semibold">{u.code}</strong>
              <span className="text-muted">{u.what}</span>
            </Chip>
          </li>
        ))}
      </ul>
    </div>
  );
}

const BOARD_SHOWN = 3;

const SHOW_DISMISSED = "/candidates?dismissed=1";

/** The latest scored week's Candidate bucket: an Evidence ring, the name, a dot per kind of evidence and why. Both lines
 * wrap (two lines at most) rather than cut off; the row's title has the name and every fired signal in full. `hidden`
 * names a dismissal still hides, counted under the rows as Candidates counts them, so the headline's and the funnel's
 * count (the digest's) adds up (PR 6 final review DT-3); `waiting`: no digest yet, so no week to speak of. */
function Board({ rows, hidden, waiting }: { rows: ScreenerRow[]; hidden: number; waiting: boolean }) {
  if (rows.length === 0) {
    if (hidden > 0) {
      return (
        <Empty
          action={
            <Link href={SHOW_DISMISSED} className={buttonVariants({ variant: "secondary", size: "sm" })}>
              Show dismissed
            </Link>
          }
        >
          Every name on the board is dismissed until the evidence changes.
        </Empty>
      );
    }
    if (waiting) return <Empty>Nothing on the board yet.</Empty>;
    return (
      <Empty
        action={
          <Link href="/candidates?bucket=early" className={buttonVariants({ variant: "secondary", size: "sm" })}>
            See Early
          </Link>
        }
      >
        Nothing on the board this week.
      </Empty>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <ByMarket rows={rows} empty="nothing on the board" />
      {hidden > 0 ? (
        <p className="text-[13px] text-muted">
          {hidden} dismissed until the evidence changes ·{" "}
          <Link href={SHOW_DISMISSED} className="inline-flex min-h-11 items-center md:min-h-0">
            show<span className="sr-only"> dismissed names</span>
          </Link>
        </p>
      ) : null}
    </div>
  );
}

/** A list of names per market, the US first, at most BOARD_SHOWN each; a market with none says so in one line (each
 * market has its own board: docs/SPEC_ISSUES.md 56). */
function ByMarket({ rows, empty }: { rows: ScreenerRow[]; empty: string }) {
  return (
    <div className="flex flex-col gap-3">
      {byMarket(rows).map(([m, list]) =>
        list.length === 0 ? (
          <p key={m} className="text-[13px] text-muted">
            {MARKET_LABEL[m]}: {empty} this week.
          </p>
        ) : (
          <div key={m} className="flex flex-col gap-2">
            <p className="eyebrow">{MARKET_LABEL[m]}</p>
            <ul aria-label={MARKET_LABEL[m]} className="flex flex-col gap-2">
              {list.slice(0, BOARD_SHOWN).map((r) => (
                <li key={r.company_id}>
                  <Link
                    href={`/company/${r.company_id}`}
                    title={`${code(r)} ${r.name}: ${boardWhyAll(r.fired_signals)}`}
                    className="tile flex items-center gap-3 p-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
                  >
                    <ScoreRing value={Number(r.evidence)} kind="evidence" />
                    <span className="flex min-w-0 flex-col gap-1">
                      <span className="line-clamp-2 text-[15px] leading-snug font-bold">
                        {code(r)} <span className="font-medium text-muted">{r.name}</span>
                      </span>
                      <span className="flex min-w-0 items-start gap-2 text-[13px] leading-snug text-muted">
                        <DotRow tones={r.families.map(familyTone)} className="mt-[3px] shrink-0" />
                        <span className="line-clamp-2">{boardWhy(r.fired_signals)}</span>
                      </span>
                    </span>
                    <LinkPending />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
    </div>
  );
}

