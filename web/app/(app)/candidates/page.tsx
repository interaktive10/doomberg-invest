import Link from "next/link";
import { Empty, Flash, Kpi, KpiRibbon, Page } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { dismissedThisWeek, latestThesisByCompany, screen, type Bucket } from "@/lib/data";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { FAMILY_LABEL, RED_FLAG_NAME, SIGNAL_PLAIN } from "@/lib/labels";
import { FAMILIES, type ScreenSpec } from "@/lib/screener";
import { cn } from "@/lib/utils";
import { dismiss, research } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Candidates" };

// BRIEF §6 Candidates, simplified (Manzoor, 2026-10-08): tabs Candidate · Early · Priced-in · Excluded; one row per
// company in plain words (why it's here, the two scores, red flags) with open card, research and dismiss; filters
// folded away. The C1–C4 detail is on the Company page. On a wide screen the rows line up under a column header (the
// header is decoration: each row also names its columns for screen readers).
const TABS: readonly [Bucket, string][] = [
  ["candidate", "Candidate"],
  ["early", "Early"],
  ["priced_in", "Priced-in"],
  ["excluded", "Excluded"],
];

const COLUMNS = "lg:grid-cols-[minmax(0,1.6fr)_10rem_10rem_minmax(0,2.4fr)_15rem]";

function href(q: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `/candidates?${s}` : "/candidates";
}

export default async function Candidates({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const bucket = (TABS.find(([b]) => b === one(q, "bucket"))?.[0] ?? "candidate") as Bucket;
  const market = one(q, "market") === "us" || one(q, "market") === "in" ? (one(q, "market") as "us" | "in") : undefined;
  const desk = one(q, "desk") === "yes" ? true : one(q, "desk") === "no" ? false : undefined;
  const family = FAMILIES.find((f) => f === one(q, "family"));
  const sector = one(q, "sector") || undefined;
  const showDismissed = one(q, "dismissed") === "1";
  const spec: ScreenSpec = { buckets: [bucket], limit: 2000 };
  if (market) spec.market = market;
  if (desk !== undefined) spec.capex_desk = desk;
  if (family) spec.families_all = [family];
  const all = await screen(spec);
  const sectors = [...new Set(all.map((r) => r.sector).filter((s): s is string => !!s))].sort();
  const week = all[0]?.week_end;
  const inSector = all.filter((r) => !sector || r.sector === sector);
  const [dismissed, cards] = await Promise.all([
    week ? dismissedThisWeek(week) : Promise.resolve(new Set<string>()),
    latestThesisByCompany(inSector.map((r) => r.company_id)),
  ]);
  const shown = inSector.filter((r) => showDismissed || !dismissed.has(r.company_id));
  const filters = {
    bucket,
    market,
    desk: desk === undefined ? undefined : desk ? "yes" : "no",
    family,
    sector,
    dismissed: showDismissed ? "1" : undefined,
  };
  const back = href(filters);
  const filtered = market !== undefined || desk !== undefined || family !== undefined || sector !== undefined;
  // The ribbon: what the list below holds (no link, no company name: the list's links and names stay unique).
  const strongest = shown.reduce<(typeof shown)[number] | undefined>((best, r) => (best === undefined || r.evidence > best.evidence ? r : best), undefined);
  const flagged = shown.filter((r) => r.red_flags.length > 0);
  const withCard = shown.filter((r) => cards.has(r.company_id)).length;
  return (
    <Page
      title="Candidates"
      description={week ? `The weekly scores for the week ending ${week}. Research only: nothing here is a trade.` : "The weekly scores, by bucket."}
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <KpiRibbon>
        <Kpi
          label="Shown"
          value={shown.length}
          hint={dismissed.size > 0 && !showDismissed ? `${dismissed.size} dismissed this week` : "in this bucket"}
        />
        <Kpi label="Strongest evidence" value={strongest ? num(strongest.evidence, 0) : "–"} hint={strongest ? code(strongest) : undefined} />
        <Kpi
          label="With a red flag"
          value={flagged.length}
          tone={flagged.some((r) => r.hard_flag) ? "down" : flagged.length > 0 ? "warn" : undefined}
        />
        <Kpi label="Have a card" value={withCard} hint={`of ${shown.length}`} />
      </KpiRibbon>
      <nav aria-label="Buckets" className="grid w-full grid-cols-4 self-start rounded-md border border-line bg-panel p-0.5 sm:inline-flex sm:w-auto">
        {TABS.map(([b, text]) => (
          <Link
            key={b}
            href={href({ ...filters, bucket: b })}
            aria-current={b === bucket ? "page" : undefined}
            className={cn(
              "inline-flex h-7 items-center justify-center rounded-sm px-2 text-[13px] font-medium no-underline transition-colors sm:px-3",
              b === bucket ? "bg-raised text-fg shadow-[inset_0_-2px_0_var(--color-accent)] hover:text-fg" : "text-muted hover:text-fg",
            )}
          >
            {text}
          </Link>
        ))}
      </nav>
      <details className="rounded-md border border-line bg-panel" open={filtered}>
        <summary className="list-none px-4 py-2.5 text-[13px] font-medium text-muted [&::-webkit-details-marker]:hidden">
          Filters{filtered ? " (on)" : ""}
        </summary>
        <form method="get" action="/candidates" className="grid grid-cols-2 items-end gap-3 border-t border-line p-4 sm:flex sm:flex-wrap">
          <input type="hidden" name="bucket" value={bucket} />
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="f-market">Market</Label>
            <Select id="f-market" name="market" defaultValue={market ?? ""} className="w-full sm:w-auto">
              <option value="">All</option>
              <option value="us">US</option>
              <option value="in">India</option>
            </Select>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="f-desk">Desk</Label>
            <Select id="f-desk" name="desk" defaultValue={filters.desk ?? ""} className="w-full sm:w-auto">
              <option value="">All</option>
              <option value="yes">Capex Desk</option>
              <option value="no">Not the desk</option>
            </Select>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="f-sector">Sector</Label>
            <Select id="f-sector" name="sector" defaultValue={sector ?? ""} className="w-full sm:w-auto sm:max-w-56">
              <option value="">All</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="f-family">Family</Label>
            <Select id="f-family" name="family" defaultValue={family ?? ""} className="w-full sm:w-auto">
              <option value="">All</option>
              {FAMILIES.map((f) => (
                <option key={f} value={f}>
                  {FAMILY_LABEL[f]}
                </option>
              ))}
            </Select>
          </div>
          <div className="col-span-2 flex h-8 items-center gap-2 sm:col-span-1">
            <input id="f-dismissed" type="checkbox" name="dismissed" value="1" defaultChecked={showDismissed} />
            <Label htmlFor="f-dismissed" className="font-normal">
              Show dismissed
            </Label>
          </div>
          <div className="col-span-2 flex items-center gap-3 sm:col-span-1">
            <Button type="submit" variant="outline">
              Filter
            </Button>
            {filtered ? (
              <Link href={href({ bucket, dismissed: filters.dismissed })} className="text-[13px]">
                Clear filters
              </Link>
            ) : null}
          </div>
        </form>
      </details>
      {shown.length === 0 ? (
        <Empty>
          {all.length === 0 && !filtered
            ? week === undefined
              ? "No scored week yet. The weekly run scores the universe each Saturday."
              : "Nothing in this bucket this week."
            : "Nothing in this bucket with these filters."}
        </Empty>
      ) : (
        <div className="rounded-md border border-line bg-panel">
          <div aria-hidden="true" className={cn("caps hidden rounded-t-md border-b border-line-strong bg-raised px-4 py-2 lg:grid lg:gap-x-6", COLUMNS)}>
            <span>Company</span>
            <span>Strength of evidence</span>
            <span>Not priced in yet</span>
            <span>Why it&apos;s here</span>
            <span />
          </div>
          <ul aria-label="Candidates">
            {shown.map((r) => {
              const card = cards.get(r.company_id);
              const gone = dismissed.has(r.company_id);
              const reasons = r.fired_signals.map((s) => SIGNAL_PLAIN[s] ?? s);
              return (
                <li
                  key={r.company_id}
                  className={cn(
                    "flex flex-col gap-3 border-t border-line p-4 first:border-t-0 lg:grid lg:items-start lg:gap-x-6 lg:gap-y-0 lg:py-3",
                    COLUMNS,
                  )}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Link href={`/company/${r.company_id}`} className="link-quiet text-sm font-semibold">
                        {r.name}
                      </Link>
                      {gone ? <Badge variant="secondary">dismissed</Badge> : null}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-muted">
                      {code(r)} · {r.market === "us" ? "US" : "India"}
                      {r.sector ? ` · ${r.sector}` : ""}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 lg:contents">
                    <Score label="Strength of evidence" value={r.evidence} />
                    <Score label="Not priced in yet" value={r.gap} />
                  </div>
                  <div className="min-w-0">
                    <div className="caps lg:sr-only">Why it&apos;s here</div>
                    {reasons.length === 0 ? (
                      <p className="mt-1 text-[13px] text-muted lg:mt-0">No signal fired.</p>
                    ) : (
                      <ul className="mt-1.5 flex flex-wrap gap-1.5 lg:mt-0">
                        {reasons.map((t) => (
                          <li key={t} className="rounded-sm bg-raised px-2 py-0.5 text-xs text-muted ring-1 ring-line-strong ring-inset">
                            {t}
                          </li>
                        ))}
                      </ul>
                    )}
                    {r.red_flags.length > 0 ? (
                      <p className={cn("mt-2 text-xs font-medium", r.hard_flag ? "text-down" : "text-warn")}>
                        Watch out: {r.red_flags.map((f) => RED_FLAG_NAME[f] ?? f).join("; ")}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-start gap-2 border-t border-line pt-3 lg:justify-end lg:border-0 lg:pt-0">
                    {card ? (
                      <Link href={`/theses/${card.id}`} className={buttonVariants({ size: "sm" })}>
                        Open card
                      </Link>
                    ) : (
                      <form action={research}>
                        <input type="hidden" name="company_id" value={r.company_id} />
                        <input type="hidden" name="week_end" value={r.week_end} />
                        <input type="hidden" name="back" value={back} />
                        <SubmitButton size="sm">Research</SubmitButton>
                      </form>
                    )}
                    {gone ? null : (
                      <details className="group/dismiss">
                        <summary className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "list-none [&::-webkit-details-marker]:hidden")}>
                          Dismiss
                        </summary>
                        <form action={dismiss} className="mt-2 flex w-56 flex-col gap-1.5 rounded-sm border border-line-strong bg-raised p-3">
                          <input type="hidden" name="company_id" value={r.company_id} />
                          <input type="hidden" name="week_end" value={r.week_end} />
                          <input type="hidden" name="back" value={back} />
                          <Label htmlFor={`reason-${r.company_id}`} className="text-xs">
                            Reason
                          </Label>
                          <Input id={`reason-${r.company_id}`} name="reason" required className="w-full" />
                          <SubmitButton size="xs" variant="outline">
                            Dismiss for this week
                          </SubmitButton>
                        </form>
                      </details>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Page>
  );
}

/** A 0–100 score with a bar; the number is the value, the bar decoration. On a wide screen the column header names it
 * (the label stays for screen readers). */
function Score({ label, value }: { label: string; value: number | string | null | undefined }) {
  const n = value === null || value === undefined || value === "" ? null : Number(value);
  const width = n === null || !Number.isFinite(n) ? 0 : Math.max(0, Math.min(100, n));
  return (
    <div className="min-w-0">
      <div className="caps lg:sr-only">{label}</div>
      <div className="mt-1 flex items-center gap-2 lg:mt-0">
        <span className="num text-lg font-semibold text-fg">{num(value, 0)}</span>
        <span aria-hidden="true" className="h-1 flex-1 overflow-hidden bg-line-strong">
          <span className="block h-full bg-accent" style={{ width: `${width}%` }} />
        </span>
      </div>
    </div>
  );
}
