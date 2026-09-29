import Link from "next/link";
import { Empty, Flash, Page } from "@/components/page";
import { FamilyBadges, FlagBadges, ScoreBar, SignalBadges } from "@/components/score";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { dismissedThisWeek, latestThesisByCompany, screen, type Bucket } from "@/lib/data";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { CONTEXT_NAME, FAMILY_LABEL } from "@/lib/labels";
import { FAMILIES, type ScreenSpec } from "@/lib/screener";
import { cn } from "@/lib/utils";
import { dismiss, research } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Candidates" };

// BRIEF §6 Candidates: tabs Candidate · Early · Priced-in · Excluded; filters market, desk, sector, family; columns
// company, market, Evidence, Gap, families, top signals, red flags, C1–C4; actions open card, research, dismiss. The
// actions sit under the company's name, which stays in view while the table scrolls on a phone.
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
  const dismissed = week ? await dismissedThisWeek(week) : new Set<string>();
  const inSector = all.filter((r) => !sector || r.sector === sector);
  const shown = inSector.filter((r) => showDismissed || !dismissed.has(r.company_id));
  const cards = await latestThesisByCompany(shown.map((r) => r.company_id));
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
      <nav aria-label="Buckets" className="grid grid-cols-4 gap-1 rounded-lg border border-gray-200 bg-white p-1 shadow-sm sm:inline-flex sm:self-start">
        {TABS.map(([b, text]) => (
          <Link
            key={b}
            href={href({ ...filters, bucket: b })}
            aria-current={b === bucket ? "page" : undefined}
            className={cn(
              "rounded-md px-2 py-1.5 text-center text-sm font-medium no-underline transition-colors sm:px-4",
              b === bucket ? "bg-gray-900 text-white hover:text-white" : "text-gray-700 hover:bg-gray-100 hover:text-gray-900",
            )}
          >
            {text}
          </Link>
        ))}
      </nav>
      <form
        method="get"
        action="/candidates"
        className="grid grid-cols-2 items-end gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:flex sm:flex-wrap"
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
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <p className="border-b border-gray-200 px-4 py-2.5 text-sm text-gray-700">
          <span className="font-medium text-gray-900">{shown.length} shown</span>
          {dismissed.size > 0 && !showDismissed ? ` · ${dismissed.size} dismissed this week` : ""}
          {week ? ` · week ending ${week}` : ""}
        </p>
        {shown.length === 0 ? (
          <div className="p-4">
            <Empty>
              {all.length === 0 && !filtered
                ? week === undefined
                  ? "No scored week yet. The weekly run scores the universe each Saturday."
                  : "Nothing in this bucket this week."
                : "Nothing in this bucket with these filters."}
            </Empty>
          </div>
        ) : (
          <Table label="Candidates">
            <TableHeader>
              <TableRow>
                <TableHead sticky>Company</TableHead>
                <TableHead>Market</TableHead>
                <TableHead num>Evidence</TableHead>
                <TableHead num>Gap</TableHead>
                <TableHead>Families</TableHead>
                <TableHead>Top signals</TableHead>
                <TableHead>Red flags</TableHead>
                {(["C1", "C2", "C3", "C4"] as const).map((c) => (
                  <TableHead key={c} num>
                    <abbr title={CONTEXT_NAME[c]}>{c}</abbr>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((r) => {
                const card = cards.get(r.company_id);
                const gone = dismissed.has(r.company_id);
                return (
                  <TableRow key={r.company_id}>
                    <TableCell sticky className="min-w-44 sm:min-w-56">
                      <Link href={`/company/${r.company_id}`} className="link-quiet">
                        {r.name}
                      </Link>{" "}
                      <span className="text-xs text-gray-700">({code(r)})</span>
                      <div className="mt-2 flex flex-wrap items-start gap-1.5">
                        {card ? (
                          <Link href={`/theses/${card.id}`} className={buttonVariants({ variant: "outline", size: "xs" })}>
                            Open card
                          </Link>
                        ) : (
                          <form action={research}>
                            <input type="hidden" name="company_id" value={r.company_id} />
                            <input type="hidden" name="week_end" value={r.week_end} />
                            <input type="hidden" name="back" value={back} />
                            <SubmitButton size="xs">Research</SubmitButton>
                          </form>
                        )}
                        {gone ? (
                          <Badge variant="secondary">dismissed</Badge>
                        ) : (
                          <details className="group/dismiss">
                            <summary className={cn(buttonVariants({ variant: "ghost", size: "xs" }), "list-none [&::-webkit-details-marker]:hidden")}>
                              Dismiss
                            </summary>
                            <form action={dismiss} className="mt-2 flex w-52 flex-col gap-1.5 rounded-lg border border-gray-200 bg-white p-2.5 shadow-sm">
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
                    </TableCell>
                    <TableCell>{r.market.toUpperCase()}</TableCell>
                    <TableCell num>
                      <ScoreBar value={r.evidence} />
                    </TableCell>
                    <TableCell num>
                      <ScoreBar value={r.gap} />
                    </TableCell>
                    <TableCell>
                      <FamilyBadges ids={r.families} />
                    </TableCell>
                    <TableCell>
                      <SignalBadges ids={r.fired_signals.slice(0, 5)} />
                    </TableCell>
                    <TableCell>
                      <FlagBadges ids={r.red_flags} hard={r.hard_flag} />
                    </TableCell>
                    <TableCell num>{num(r.c1, 0)}</TableCell>
                    <TableCell num>{num(r.c2, 0)}</TableCell>
                    <TableCell num>{num(r.c3, 0)}</TableCell>
                    <TableCell num>{num(r.c4, 0)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </Page>
  );
}
