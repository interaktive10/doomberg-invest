import Link from "next/link";
import { Empty, Flash, Page } from "@/components/page";
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

// BRIEF §6 Candidates, simplified (Manzoor, 2026-10-08): tabs Candidate · Early · Priced-in · Excluded; one card per
// company in plain words (why it's here, the two scores, red flags) with open card, research and dismiss; filters
// folded away. The C1–C4 detail is on the Company page.
const TABS: readonly [Bucket, string][] = [
  ["candidate", "Candidate"],
  ["early", "Early"],
  ["priced_in", "Priced-in"],
  ["excluded", "Excluded"],
];

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
  return (
    <Page
      title="Candidates"
      description={week ? `The weekly scores for the week ending ${week}. Research only: nothing here is a trade.` : "The weekly scores, by bucket."}
    >
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <nav aria-label="Buckets" className="grid grid-cols-4 gap-1 rounded-xl bg-gray-100 p-1 sm:inline-flex sm:self-start">
        {TABS.map(([b, text]) => (
          <Link
            key={b}
            href={href({ ...filters, bucket: b })}
            aria-current={b === bucket ? "page" : undefined}
            className={cn(
              "rounded-lg px-2 py-1.5 text-center text-sm font-medium no-underline transition-colors sm:px-4",
              b === bucket ? "bg-white text-gray-900 shadow-sm ring-1 ring-gray-200 hover:text-gray-900" : "text-gray-600 hover:text-gray-900",
            )}
          >
            {text}
          </Link>
        ))}
      </nav>
      <details className="group rounded-2xl border border-gray-200/80 bg-white" open={filtered}>
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-gray-700 [&::-webkit-details-marker]:hidden">
          Filters{filtered ? " (on)" : ""}
        </summary>
      <form
        method="get"
        action="/candidates"
        className="grid grid-cols-2 items-end gap-3 border-t border-gray-100 p-4 sm:flex sm:flex-wrap"
      >
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
        <div className="col-span-2 flex h-9 items-center gap-2 sm:col-span-1">
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
            <Link href={href({ bucket, dismissed: filters.dismissed })} className="text-sm">
              Clear filters
            </Link>
          ) : null}
        </div>
      </form>
      </details>
      <p className="text-sm text-gray-600">
        <span className="font-medium text-gray-900">{shown.length} shown</span>
        {dismissed.size > 0 && !showDismissed ? ` · ${dismissed.size} dismissed this week` : ""}
      </p>
      {shown.length === 0 ? (
        <Empty>
          {all.length === 0 && !filtered
            ? week === undefined
              ? "No scored week yet. The weekly run scores the universe each Saturday."
              : "Nothing in this bucket this week."
            : "Nothing in this bucket with these filters."}
        </Empty>
      ) : (
        <ul aria-label="Candidates" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {shown.map((r) => {
            const card = cards.get(r.company_id);
            const gone = dismissed.has(r.company_id);
            const reasons = r.fired_signals.map((s) => SIGNAL_PLAIN[s] ?? s);
            return (
              <li key={r.company_id} className="flex flex-col gap-4 rounded-2xl border border-gray-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/company/${r.company_id}`} className="link-quiet text-base font-semibold">
                      {r.name}
                    </Link>
                    <div className="mt-0.5 text-sm text-gray-600">
                      {code(r)} · {r.market === "us" ? "US" : "India"}
                      {r.sector ? ` · ${r.sector}` : ""}
                    </div>
                  </div>
                  {gone ? <Badge variant="secondary">dismissed</Badge> : null}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Score label="Strength of evidence" value={r.evidence} />
                  <Score label="Not priced in yet" value={r.gap} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-600">Why it&apos;s here</div>
                  {reasons.length === 0 ? (
                    <p className="mt-1 text-sm text-gray-700">No signal fired.</p>
                  ) : (
                    <ul className="mt-1.5 flex flex-wrap gap-1.5">
                      {reasons.map((t) => (
                        <li key={t} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-800">
                          {t}
                        </li>
                      ))}
                    </ul>
                  )}
                  {r.red_flags.length > 0 ? (
                    <p className={cn("mt-2 text-xs font-medium", r.hard_flag ? "text-red-800" : "text-amber-900")}>
                      Watch out: {r.red_flags.map((f) => RED_FLAG_NAME[f] ?? f).join("; ")}
                    </p>
                  ) : null}
                </div>
                <div className="mt-auto flex flex-wrap items-start gap-2 border-t border-gray-100 pt-4">
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
                      <form action={dismiss} className="mt-2 flex w-56 flex-col gap-1.5 rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                        <input type="hidden" name="company_id" value={r.company_id} />
                        <input type="hidden" name="week_end" value={r.week_end} />
                        <input type="hidden" name="back" value={back} />
                        <Label htmlFor={`reason-${r.company_id}`} className="text-xs">
                          Reason
                        </Label>
                        <Input id={`reason-${r.company_id}`} name="reason" required className="h-8 w-full" />
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
      )}
    </Page>
  );
}

/** A 0–100 score with a bar; the number is the value, the bar decoration. */
function Score({ label, value }: { label: string; value: number | string | null | undefined }) {
  const n = value === null || value === undefined || value === "" ? null : Number(value);
  const width = n === null || !Number.isFinite(n) ? 0 : Math.max(0, Math.min(100, n));
  return (
    <div>
      <div className="text-xs font-medium text-gray-600">{label}</div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-lg font-semibold tabular-nums text-gray-900">{num(value, 0)}</span>
        <span aria-hidden="true" className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
          <span className="block h-full rounded-full bg-blue-600" style={{ width: `${width}%` }} />
        </span>
      </div>
    </div>
  );
}
