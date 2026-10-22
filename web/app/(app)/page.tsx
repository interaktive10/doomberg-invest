import Link from "next/link";
import { Callout } from "@/components/callout";
import { Chip, Dot, DotRow } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Icon, type IconName } from "@/components/icons";
import { Markdown } from "@/components/markdown";
import { Empty, Page, Section } from "@/components/page";
import { ScoreRing } from "@/components/score-ring";
import { TickerTile } from "@/components/ticker-tile";
import { buttonVariants } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { ensureReviews, latestDigest, screen, sourceHealth, theses, thesisFigures, type ScreenerRow, type Thesis } from "@/lib/data";
import { dayDate, weekEyebrow } from "@/lib/dates";
import { code } from "@/lib/format";
import {
  boardWhy,
  changeItems,
  comingUp,
  funnelInsight,
  funnelSteps,
  funnelTitle,
  funnelTotals,
  headline,
  healthRows,
  homeSections,
  lateLine,
  parseFunnel,
  todoAsk,
  todoMinutes,
  type ChangeDir,
  type ChangeItem,
  type FunnelKey,
  type FunnelTotals,
  type HealthState,
  type Upcoming,
} from "@/lib/home";
import { familyTone, type Tone } from "@/lib/palette";
import { lateSources } from "@/lib/staleness";
import { group, markMoved } from "@/lib/theses";
import { cn } from "@/lib/utils";

export const metadata = { title: "This week" };

// BRIEF §6 Home, drawn as the overhaul PR 6 mock: the week and one line that leads with the answer; the funnel as four
// numbers with bars and its one insight (the digest's This week, the line itself under Details); To do (the Theses
// screen's Needs you group, read live) as rows with the decision each needs; What changed (the digest's section) as a
// feed with a direction and the Evidence move per line, then Coming up (the live cards' next filings); On the board
// (the Candidate bucket of the latest scored week) with Evidence rings; Data health with a dot per source the pipeline
// reads, and the stale-data line when one is late (Home alone has it). The digest's own words, codes and all, stay in
// each row's tooltip and the funnel's Details, so Home and the issue still read the same.
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, sources, first, board] = await Promise.all([
    latestDigest(),
    sourceHealth(),
    theses(),
    screen({ buckets: ["candidate"], limit: 500 }),
  ]);
  const all = markMoved(first, await ensureReviews(first)); // as the Theses screen does, so both list the same
  const needs = all.filter((t) => group(t) === "needs");
  const figures = await thesisFigures(needs);
  const { funnel, changed, legacy } = homeSections(digest?.body_md ?? "");
  const lines = parseFunnel(funnel);
  const totals = funnelTotals(lines);
  const items = changeItems(changed);
  const now = new Date();
  const kills = new Map([...figures].map(([id, f]) => [id, f.kills.length]));
  const upcoming = comingUp(all, now.toISOString().slice(0, 10), kills);
  const late = lateSources(sources, now).length;
  return (
    <Page
      eyebrow={digest ? weekEyebrow(digest.week_end) : undefined}
      title="This week"
      description={headline({ digest: digest !== null, totals, funnel, legacy })}
      actions={digest ? <AsOf week={digest.week_end} late={late} /> : undefined}
    >
      <Section id="funnel" title={totals ? funnelTitle(totals) : "This week's funnel"} quiet>
        <Funnel totals={totals} lines={lines.map((l) => l.text)} funnel={funnel} legacy={legacy} />
      </Section>
      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
          <Section
            id="todo"
            title="To do"
            count={needs.length > 0 ? needs.length : undefined}
            actions={needs.length > 0 ? <span className="text-[14px] text-subtle">about {todoMinutes(needs.length)} minutes</span> : undefined}
          >
            {needs.length === 0 ? (
              <Empty
                action={
                  <Link href="/candidates" className={buttonVariants({ variant: "secondary", size: "sm" })}>
                    See the candidates
                  </Link>
                }
              >
                Nothing needs you this week.
              </Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {needs.map((t) => (
                  <TodoRow key={t.id} t={t} f={figures.get(t.id)} />
                ))}
              </ul>
            )}
          </Section>
          <Section id="changed" title="What changed">
            {items.length > 0 ? (
              <Feed items={items} />
            ) : changed ? (
              <p className="text-[15px] text-muted">{changed}</p>
            ) : legacy ? (
              <Markdown text={legacy} />
            ) : (
              <Empty>Nothing to compare yet: What changed comes with the weekly digest.</Empty>
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
                <Link href="/candidates" className="text-[14px] font-medium no-underline">
                  All {board.length}
                  <span className="sr-only"> on the board</span>
                </Link>
              ) : undefined
            }
          >
            <Board rows={board} />
          </Section>
          <Section id="health" title="Data health" quiet>
            <Health rows={healthRows(sources, now)} late={lateLine(sources, now)} />
          </Section>
        </div>
      </div>
    </Page>
  );
}

/** "Data as of Fri, Sep 18": amber, and a link down to Data health, while a source is late. */
function AsOf({ week, late }: { week: string; late: number }) {
  const text = `Data as of ${dayDate(week)}`;
  if (late === 0) return <Chip dot="up">{text}</Chip>;
  return (
    <Link href="#health" className="inline-flex rounded-full no-underline">
      <Chip variant="warn" dot="warn">
        {text} · {late} {late === 1 ? "source" : "sources"} late
      </Chip>
    </Link>
  );
}

const FUNNEL_FILL: Record<FunnelKey, string> = {
  scored: "bg-subtle/40",
  stage: "bg-accent/45",
  board: "bg-accent",
  new: "bg-accent",
};

/** Four numbers with bars (log scale: 3 of 4,659 still shows), the one insight, and the digest's own line under
 * Details; a week without scores says why; a digest from before the funnel says so. */
function Funnel({ totals, lines, funnel, legacy }: { totals: FunnelTotals | null; lines: string[]; funnel: string; legacy: string }) {
  if (totals === null) {
    if (funnel) {
      return (
        <Callout tone="warn">
          <Markdown text={funnel} />
        </Callout>
      );
    }
    return (
      <Empty>
        {legacy
          ? "This digest predates the funnel line; Saturday's weekly run writes it."
          : "No digest yet. The weekly run writes one each Saturday, after it scores the universe."}
      </Empty>
    );
  }
  const insight = funnelInsight(totals);
  return (
    <div className="flex flex-col gap-5">
      <ol className="grid grid-cols-4 gap-3 md:gap-6">
        {funnelSteps(totals).map((s, i) => (
          <li key={s.key} className="flex min-w-0 flex-col gap-2">
            <span className="num text-[22px] leading-none font-bold tracking-[-0.03em] text-fg sm:text-[28px] md:text-[34px]">
              {s.value.toLocaleString("en-US")}
            </span>
            <span aria-hidden="true" className="block h-2 overflow-hidden rounded-full bg-track">
              <span
                className={cn("grow-x block h-full rounded-full", FUNNEL_FILL[s.key])}
                style={{ width: `${s.width}%`, animationDelay: `${i * 60}ms` }}
              />
            </span>
            <span className="text-[12px] leading-snug text-muted md:text-[13px]">{s.label}</span>
          </li>
        ))}
      </ol>
      {insight ? (
        <Callout>
          <strong className="font-semibold text-fg">{insight.lead}</strong>
          {insight.rest}
        </Callout>
      ) : null}
      <Disclosure summary="Details">
        <p>The weekly issue&apos;s line{lines.length === 1 ? "" : "s, one per market"}:</p>
        {lines.map((l) => (
          <p key={l} className="num mt-1 text-fg">
            {l}
          </p>
        ))}
      </Disclosure>
    </div>
  );
}

type Figure = { atCard: number | null; now: number | null; kills: string[] };

/** A card to accept or pass, or a review to give a verdict on: the whole row opens it. */
function TodoRow({ t, f }: { t: Thesis; f: Figure | undefined }) {
  const c = t.companies;
  const ticker = c ? code(c) : "";
  const { ask, action, alert } = todoAsk(t.state, f);
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
          <span className={cn("text-[13px]", alert ? "font-medium text-down" : "text-muted")}>{ask}</span>
        </span>
        <span className={cn(buttonVariants({ size: "sm" }), "hidden sm:inline-flex")}>{action}</span>
        <Icon name="chevron-right" className="text-subtle sm:hidden" />
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

const SHOWN = 8;

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
 * the right. The digest's line, codes and all, is the row's tooltip. */
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
          {c.delta.value}
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

const BOARD_SHOWN = 5;

/** The latest scored week's Candidate bucket: an Evidence ring, the name, a dot per kind of evidence and why. */
function Board({ rows }: { rows: ScreenerRow[] }) {
  if (rows.length === 0) {
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
    <ul className="flex flex-col gap-2">
      {rows.slice(0, BOARD_SHOWN).map((r) => (
        <li key={r.company_id}>
          <Link
            href={`/company/${r.company_id}`}
            className="tile flex items-center gap-3 p-2.5 text-fg no-underline transition-colors duration-150 hover:bg-hover hover:text-fg"
          >
            <ScoreRing value={Number(r.evidence)} kind="evidence" />
            <span className="flex min-w-0 flex-col gap-1">
              <span className="truncate text-[15px] font-bold">
                {code(r)} <span className="font-medium text-muted">{r.name}</span>
              </span>
              <span className="flex min-w-0 items-center gap-2 text-[13px] text-muted">
                <DotRow tones={r.families.map(familyTone)} />
                <span className="truncate">{boardWhy(r.fired_signals)}</span>
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

const HEALTH_DOT: Record<HealthState, Tone> = { ok: "up", late: "warn", down: "down", resting: "muted" };
const HEALTH_TEXT: Record<HealthState, string> = { ok: "text-subtle", late: "text-warn", down: "text-down", resting: "text-subtle" };

/** A dot and a date per source the pipeline reads; the stale-data line (BRIEF §2.7) under them when one is late. */
function Health({ rows, late }: { rows: ReturnType<typeof healthRows>; late: string | null }) {
  return (
    <div className="flex flex-col gap-3">
      {rows.length === 0 ? (
        <p className="text-[14px] text-muted">No source has reported yet.</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {rows.map((h) => (
            <li key={h.source} className="flex items-center gap-2.5 text-[14px]">
              <Dot tone={HEALTH_DOT[h.state]} />
              <span className="flex-1 text-fg">{h.name}</span>
              <span className={cn("num", HEALTH_TEXT[h.state])}>{h.when}</span>
            </li>
          ))}
        </ul>
      )}
      {late ? (
        <Callout tone="warn">
          {late} Each source&apos;s last success and error are under <Link href="/settings#sources">Sources</Link> in Settings.
        </Callout>
      ) : null}
    </div>
  );
}
