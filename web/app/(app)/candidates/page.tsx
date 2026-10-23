import Link from "next/link";
import { Chip, Legend } from "@/components/chip";
import { DetailsMenu } from "@/components/details-menu";
import { Icon } from "@/components/icons";
import { Empty, Flash, Page } from "@/components/page";
import { ScoreTile } from "@/components/score-ring";
import { Segmented } from "@/components/segmented";
import { SubmitButton } from "@/components/submit-button";
import { TickerTile } from "@/components/ticker-tile";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { requireUser } from "@/lib/auth";
import {
  BUCKET_EMPTY,
  BUCKET_LINE,
  BUCKET_RANGE,
  BUCKET_TABS,
  evidenceChange,
  evidenceMove,
  EVIDENCE_MOVE,
  flagLine,
  isNew,
  stillDismissed,
  windowStart,
  type ShownBucket,
} from "@/lib/candidates";
import { dismissals, latestDigest, latestThesisByCompany, scoreHistory, screen, type ScreenerRow, type Thesis } from "@/lib/data";
import { weekEyebrow } from "@/lib/dates";
import { code } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { changeItems, homeSections, leftBucket, shownDelta, type ChangeItem } from "@/lib/home";
import { FAMILY_LABEL, SIGNAL_NAME, SIGNAL_PLAIN } from "@/lib/labels";
import { signalTone } from "@/lib/palette";
import type { ScreenSpec } from "@/lib/screener";
import { cn } from "@/lib/utils";
import { dismiss, research } from "./actions";

export const metadata = { title: "Candidates" };

// BRIEF §6 Candidates (overhaul PR 4: one entry per company in plain words, filters folded away), drawn as the overhaul
// PR 6 mock: a segmented switch for the three buckets (Candidate is "On the board"), then one card per company with its
// ticker tile, the Evidence and Gap rings, the Evidence change since its previous scores row (none under a NEW name,
// which has no earlier row), why it's here as chips with a dot per family (the codes in their tooltips), the red-flag
// line, NEW when it is in the bucket for the first time in 12 weeks, and Open / Open card or Research / Dismiss. A
// dismissal holds until the evidence changes (lib/candidates.ts). Under the cards, the names that left this bucket
// this week (the digest's What changed lines, when the digest is of the week shown) and a legend. Before the first
// weekly run (no digest, no scores) it says so, with no filters and no button to an Early tab as empty (PR 6 final
// review).

const FAMILIES = Object.keys(FAMILY_LABEL);

const LEFT_TITLE: Record<ShownBucket, string> = {
  candidate: "Left the board this week",
  early: "Left Early this week",
  priced_in: "No longer priced in this week",
};

function href(q: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `/candidates?${s}` : "/candidates";
}

function score(v: number | string | null | undefined): number | null {
  const n = v === null || v === undefined || v === "" ? Number.NaN : Number(v);
  return Number.isFinite(n) ? n : null;
}

export default async function Candidates({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const bucket: ShownBucket = BUCKET_TABS.find(([b]) => b === one(q, "bucket"))?.[0] ?? "candidate";
  const market = one(q, "market") === "us" || one(q, "market") === "in" ? (one(q, "market") as "us" | "in") : undefined;
  const family = FAMILIES.find((f) => f === one(q, "family"));
  const sector = one(q, "sector") || undefined;
  const showDismissed = one(q, "dismissed") === "1";
  const spec: ScreenSpec = { buckets: [bucket], limit: 2000 };
  if (market) spec.market = market;
  if (family) spec.families_all = [family];
  const all = await screen(spec);
  const sectors = [...new Set(all.map((r) => r.sector).filter((s): s is string => !!s))].sort();
  const week = all[0]?.week_end;
  const inSector = all.filter((r) => !sector || r.sector === sector);
  const ids = inSector.map((r) => r.company_id);
  const [held, cards, history, digest] = await Promise.all([
    week ? dismissals(ids, week) : Promise.resolve(new Map<string, never>()),
    latestThesisByCompany(ids),
    week ? scoreHistory(ids, windowStart(week), week) : Promise.resolve(new Map<string, never[]>()),
    latestDigest(),
  ]);
  // still dismissed: no week since the dismissal (this one included) had a new signal or family or moved Evidence 10
  // (Home's On the board leaves out the same names)
  const dismissed = stillDismissed(inSector, held);
  const shown = inSector.filter((r) => showDismissed || !dismissed.has(r.company_id));
  const filters = { bucket, market, family, sector, dismissed: showDismissed ? "1" : undefined };
  const back = href(filters);
  const filtered = market !== undefined || family !== undefined || sector !== undefined;
  const hidden = showDismissed ? 0 : inSector.length - shown.length;
  const firstRun = digest === null && week === undefined && !filtered;
  // the digest's lines about names that left this bucket, only when it is the digest of the week shown
  const left = digest && week && digest.week_end === week ? leftBucket(changeItems(homeSections(digest.body_md).changed), bucket) : [];
  const range = BUCKET_RANGE[bucket];
  return (
    <Page
      eyebrow={week ? weekEyebrow(week, false) : undefined}
      title="Candidates"
      description={BUCKET_LINE[bucket]}
      actions={
        <Segmented
          label="Buckets"
          items={BUCKET_TABS.map(([b, text]) => ({
            href: href({ ...filters, bucket: b }),
            label: text,
            count: b === bucket ? shown.length : undefined,
            current: b === bucket,
          }))}
        />
      }
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      {firstRun ? null : (
        <div className="flex flex-wrap items-center gap-3">
          {shown.length > 0 || hidden > 0 ? (
            <p className="text-[14px] text-muted">
              {shown.length} {shown.length === 1 ? "name" : "names"}
              {hidden > 0 ? (
                <>
                  {" "}
                  · {hidden} dismissed until the evidence changes ·{" "}
                  <Link href={href({ ...filters, dismissed: "1" })} className="inline-flex min-h-11 items-center md:min-h-0">
                    show
                  </Link>
                </>
              ) : null}
              {showDismissed ? " · dismissed ones shown" : ""}
            </p>
          ) : null}
          <Filters bucket={bucket} market={market} family={family} sector={sector} sectors={sectors} showDismissed={showDismissed} filtered={filtered} />
        </div>
      )}
      {shown.length === 0 ? (
        // on the canvas, so the outline button (a secondary one has no edge there; PR 6 final review L5-4)
        <Empty
          action={
            filtered ? (
              <Link href={href({ bucket, dismissed: filters.dismissed })} className={buttonVariants({ variant: "outline", size: "sm" })}>
                Clear filters
              </Link>
            ) : bucket === "candidate" && !firstRun ? (
              <Link href={href({ ...filters, bucket: "early" })} className={buttonVariants({ variant: "outline", size: "sm" })}>
                See Early
              </Link>
            ) : undefined
          }
        >
          {filtered
            ? "Nothing here with these filters."
            : firstRun
              ? "No scores yet: the weekly run writes the first on Saturday."
              : inSector.length > 0
                ? "Every name here is dismissed until the evidence changes."
                : BUCKET_EMPTY[bucket]}
        </Empty>
      ) : (
        <ul aria-label="Candidates" className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,20rem),1fr))] gap-5">
          {shown.map((r, i) => (
            <CandidateCard
              key={r.company_id}
              r={r}
              i={i}
              card={cards.get(r.company_id)}
              gone={dismissed.has(r.company_id)}
              fresh={isNew(r.bucket, r.week_end, history.get(r.company_id) ?? [])}
              change={evidenceChange(r.evidence, r.week_end, history.get(r.company_id) ?? [])}
              back={back}
            />
          ))}
        </ul>
      )}
      {left.length > 0 ? <Left title={LEFT_TITLE[bucket]} items={left} /> : null}
      {/* before the first weekly run there are no rings or dots to explain (PR 6 re-review FR-2) */}
      {firstRun ? null : (
        <Legend
          className="rounded-[20px] border border-dashed border-line-strong px-5 py-4"
          items={[
            { tone: "evidence", label: <><strong className="font-semibold text-fg">Evidence</strong> how many independent kinds of signal agree ({range.evidence})</> },
            { tone: "gap", label: <><strong className="font-semibold text-fg">Gap</strong> how far the price lags them ({range.gap})</> },
            { tone: "business", label: "business" },
            { tone: "insiders", label: "insiders" },
            { tone: "ownership", label: "ownership" },
            { tone: "text", label: "text facts" },
          ]}
        />
      )}
    </Page>
  );
}

const MOVE: Record<"up" | "down" | "flat", { icon: "arrow-up" | "arrow-down" | "minus"; text: string }> = {
  up: { icon: "arrow-up", text: "text-up" },
  down: { icon: "arrow-down", text: "text-down" },
  flat: { icon: "minus", text: "text-muted" },
};

const FLAG: Record<"good" | "warn" | "bad", string> = { good: "text-muted", warn: "text-warn", bad: "text-down" };

/** One company: who it is, the two rings, the Evidence change, why it's here, its red flags, and what to do. */
function CandidateCard({
  r,
  i,
  card,
  gone,
  fresh,
  change,
  back,
}: {
  r: ScreenerRow;
  i: number;
  card: Pick<Thesis, "id"> | undefined;
  gone: boolean;
  fresh: boolean;
  change: { change: number; since: string } | null;
  back: string;
}) {
  const ticker = code(r);
  const nameId = `name-${r.company_id}`;
  const move = evidenceMove(change);
  const flags = flagLine(r.red_flags, r.hard_flag);
  return (
    <li className="sheet rise flex min-w-0 flex-col gap-4 p-5" style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
      <div className="flex items-center gap-3">
        <TickerTile ticker={ticker} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h2 id={nameId} className="text-[18px] leading-tight font-bold tracking-[-0.01em] text-fg">
              {r.name}
            </h2>
            {fresh ? <Badge title="In this bucket for the first time in 12 weeks">NEW</Badge> : null}
            {gone ? <Badge variant="secondary">dismissed</Badge> : null}
          </div>
          <p className="truncate text-[13px] text-subtle">{[ticker, r.market === "in" ? "India" : null, r.sector].filter(Boolean).join(" · ")}</p>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex gap-3">
          <ScoreTile value={score(r.evidence)} kind="evidence" />
          <ScoreTile value={score(r.gap)} kind="gap" />
        </div>
        {change !== null ? (
          <p className={cn("flex items-center gap-1.5 text-[13px]", MOVE[move.tone].text)}>
            <Icon name={MOVE[move.tone].icon} className="size-3.5" strokeWidth={2.4} />
            <span>
              <span className="font-semibold">Evidence</span> {move.text}
            </span>
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-2">
        <p className="eyebrow">Why it&apos;s here</p>
        {r.fired_signals.length === 0 ? (
          <p className="text-[13px] text-muted">No signal fired.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {r.fired_signals.map((s) => (
              <li key={s}>
                <Chip dot={signalTone(s)} title={SIGNAL_NAME[s] ? `${s} ${SIGNAL_NAME[s]}` : s}>
                  {SIGNAL_PLAIN[s] ?? s}
                </Chip>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className={cn("flex items-start gap-2 text-[13px]", FLAG[flags.tone])} title={flags.codes || undefined}>
        <Icon name="shield" className={cn("mt-px", flags.tone === "good" && "text-subtle")} />
        <span>{flags.text}</span>
      </p>
      <div className="mt-auto flex items-center gap-2">
        <Link href={`/company/${r.company_id}`} className={cn(buttonVariants(), "flex-1")}>
          Open<span className="sr-only"> {r.name}</span>
        </Link>
        {card ? (
          <Link href={`/theses/${card.id}`} aria-describedby={nameId} className={buttonVariants({ variant: "secondary" })}>
            Open card
          </Link>
        ) : (
          <form action={research}>
            <input type="hidden" name="company_id" value={r.company_id} />
            <input type="hidden" name="back" value={back} />
            <SubmitButton variant="secondary" aria-describedby={nameId}>
              Research
            </SubmitButton>
          </form>
        )}
        {gone ? null : <Dismiss r={r} back={back} />}
      </div>
    </li>
  );
}

/** Dismiss, with its reason, from a small form that opens above the button (a native disclosure: no script; with
 * script it also closes on a click outside or on Escape, like the More menu). */
function Dismiss({ r, back }: { r: ScreenerRow; back: string }) {
  return (
    <DetailsMenu className="group/dismiss relative">
      <summary
        title="Dismiss: hide it until the evidence changes"
        className={cn(buttonVariants({ variant: "secondary", size: "icon" }), "list-none text-muted [&::-webkit-details-marker]:hidden")}
      >
        <Icon name="x" strokeWidth={2.2} />
        <span className="sr-only">Dismiss {r.name}</span>
      </summary>
      <form action={dismiss} className="pop absolute right-0 bottom-full z-30 mb-2 flex w-72 max-w-[calc(100vw-3rem)] flex-col gap-2 rounded-tile p-4">
        <input type="hidden" name="company_id" value={r.company_id} />
        <input type="hidden" name="week_end" value={r.week_end} />
        <input type="hidden" name="back" value={back} />
        <Label htmlFor={`reason-${r.company_id}`}>Reason</Label>
        <Input id={`reason-${r.company_id}`} name="reason" required className="w-full" />
        <p className="text-[13px] text-subtle">Hidden until a new signal fires or Evidence moves {EVIDENCE_MOVE}.</p>
        <SubmitButton size="sm">Confirm dismissal</SubmitButton>
      </form>
    </DetailsMenu>
  );
}

/** Market, sector, family and show dismissed, folded behind one pill; the form opens under it (and closes on a click
 * outside or on Escape). */
function Filters({
  bucket,
  market,
  family,
  sector,
  sectors,
  showDismissed,
  filtered,
}: {
  bucket: ShownBucket;
  market: string | undefined;
  family: string | undefined;
  sector: string | undefined;
  sectors: string[];
  showDismissed: boolean;
  filtered: boolean;
}) {
  return (
    <DetailsMenu className="group/filters relative ml-auto">
      <summary className={cn(buttonVariants({ variant: "outline", size: "sm" }), "list-none [&::-webkit-details-marker]:hidden")}>
        Filters{filtered ? " · on" : ""}
        <Icon name="chevron-down" className="transition-transform duration-200 group-open/filters:rotate-180" />
      </summary>
      <form method="get" action="/candidates" className="pop absolute top-full right-0 z-30 mt-2 grid w-[min(22rem,calc(100vw-2rem))] grid-cols-2 gap-3 rounded-tile p-4">
        <input type="hidden" name="bucket" value={bucket} />
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="f-market">Market</Label>
          <Select id="f-market" name="market" defaultValue={market ?? ""} className="w-full">
            <option value="">All</option>
            <option value="us">US</option>
            <option value="in">India</option>
          </Select>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="f-family">Family</Label>
          <Select id="f-family" name="family" defaultValue={family ?? ""} className="w-full">
            <option value="">All</option>
            {FAMILIES.map((f) => (
              <option key={f} value={f}>
                {FAMILY_LABEL[f]}
              </option>
            ))}
          </Select>
        </div>
        <div className="col-span-2 flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="f-sector">Sector</Label>
          <Select id="f-sector" name="sector" defaultValue={sector ?? ""} className="w-full">
            <option value="">All</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="col-span-2 flex min-h-11 items-center gap-2">
          <input id="f-dismissed" type="checkbox" name="dismissed" value="1" defaultChecked={showDismissed} />
          <Label htmlFor="f-dismissed" className="font-normal text-fg">
            Show dismissed
          </Label>
        </div>
        <div className="col-span-2 flex items-center gap-3">
          <Button type="submit" size="sm">
            Filter
          </Button>
          {filtered ? (
            <Link href={href({ bucket, dismissed: showDismissed ? "1" : undefined })} className="inline-flex min-h-11 items-center text-[13px] md:min-h-0">
              Clear filters
            </Link>
          ) : null}
        </div>
      </form>
    </DetailsMenu>
  );
}

/** The names that left this bucket this week, quieter than the cards: what happened, why, the Evidence move. */
function Left({ title, items }: { title: string; items: ChangeItem[] }) {
  return (
    <section aria-labelledby="left" className="flex flex-col gap-2.5">
      <h2 id="left" className="eyebrow">
        {title}
      </h2>
      <ul className="flex flex-col gap-2">
        {items.map((c) => (
          <li
            key={`${c.href} ${c.raw}`}
            title={`${c.code} ${c.raw}`}
            className="flex flex-wrap items-center gap-x-3.5 gap-y-2 rounded-tile border border-dashed border-line-strong px-4 py-3"
          >
            <TickerTile ticker={c.code} size="sm" className="bg-hover text-muted" />
            <div className="flex min-w-48 flex-1 flex-col gap-0.5">
              <p className="text-[15px] font-semibold text-fg">
                {c.code} <span className="font-normal text-muted">{c.title}</span>
              </p>
              {c.why ? <p className="text-[14px] text-muted">{c.why}</p> : null}
            </div>
            {c.delta ? (
              <p className="num text-[14px] font-semibold text-warn">
                {c.delta.label} {shownDelta(c.delta.value)}
              </p>
            ) : null}
            <Link href={c.href} className={buttonVariants({ variant: "secondary", size: "sm" })}>
              Open<span className="sr-only"> {c.code}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
