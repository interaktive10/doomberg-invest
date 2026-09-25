import Link from "next/link";
import { Empty, Flash, Page } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { dismissedThisWeek, latestThesisByCompany, screen, type Bucket } from "@/lib/data";
import { code, num } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { FAMILIES, type ScreenSpec } from "@/lib/screener";
import { dismiss, research } from "./actions";

// BRIEF §6 Candidates: tabs Candidate · Early · Priced-in · Excluded; filters market, desk, sector, family; columns
// company, market, Evidence, Gap, families, top signals, red flags, C1–C4; actions open card, research, dismiss.
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
  return (
    <Page title="Candidates">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <nav aria-label="Buckets" className="mb-4 flex flex-wrap gap-2">
        {TABS.map(([b, label]) => (
          <Link
            key={b}
            href={href({ ...filters, bucket: b })}
            aria-current={b === bucket ? "page" : undefined}
            className={
              "rounded-md border px-3 py-1.5 text-sm no-underline " +
              (b === bucket ? "border-blue-800 bg-blue-800 text-white" : "border-gray-400 text-gray-900 hover:bg-gray-100")
            }
          >
            {label}
          </Link>
        ))}
      </nav>
      <form method="get" action="/candidates" className="mb-4 flex flex-wrap items-end gap-3">
        <input type="hidden" name="bucket" value={bucket} />
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-market">Market</Label>
          <Select id="f-market" name="market" defaultValue={market ?? ""}>
            <option value="">All</option>
            <option value="us">US</option>
            <option value="in">India</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-desk">Desk</Label>
          <Select id="f-desk" name="desk" defaultValue={filters.desk ?? ""}>
            <option value="">All</option>
            <option value="yes">Capex Desk</option>
            <option value="no">Not the desk</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-sector">Sector</Label>
          <Select id="f-sector" name="sector" defaultValue={sector ?? ""}>
            <option value="">All</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-family">Family</Label>
          <Select id="f-family" name="family" defaultValue={family ?? ""}>
            <option value="">All</option>
            {FAMILIES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-center gap-2 pb-2">
          <input id="f-dismissed" type="checkbox" name="dismissed" value="1" defaultChecked={showDismissed} />
          <Label htmlFor="f-dismissed">Show dismissed</Label>
        </div>
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>
      <p className="mb-2 text-sm text-gray-700">
        {week ? `Week ending ${week}. ` : ""}
        {shown.length} shown{dismissed.size > 0 && !showDismissed ? `, ${dismissed.size} dismissed this week` : ""}.
      </p>
      {shown.length === 0 ? (
        <Empty>Nothing in this bucket with these filters.</Empty>
      ) : (
        <Table label="Candidates">
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Market</TableHead>
              <TableHead>Evidence</TableHead>
              <TableHead>Gap</TableHead>
              <TableHead>Families</TableHead>
              <TableHead>Top signals</TableHead>
              <TableHead>Red flags</TableHead>
              <TableHead>C1</TableHead>
              <TableHead>C2</TableHead>
              <TableHead>C3</TableHead>
              <TableHead>C4</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((r) => {
              const card = cards.get(r.company_id);
              const gone = dismissed.has(r.company_id);
              return (
                <TableRow key={r.company_id}>
                  <TableCell>
                    <Link href={`/company/${r.company_id}`}>{r.name}</Link>{" "}
                    <span className="text-gray-700">({code(r)})</span>
                  </TableCell>
                  <TableCell>{r.market.toUpperCase()}</TableCell>
                  <TableCell>{num(r.evidence)}</TableCell>
                  <TableCell>{num(r.gap)}</TableCell>
                  <TableCell>{r.families.join(", ")}</TableCell>
                  <TableCell>{r.fired_signals.slice(0, 5).join(" ")}</TableCell>
                  <TableCell>
                    {r.red_flags.map((f) => (
                      <Badge key={f} variant={r.hard_flag ? "destructive" : "warning"} className="mr-1">
                        {f}
                      </Badge>
                    ))}
                  </TableCell>
                  <TableCell>{num(r.c1, 0)}</TableCell>
                  <TableCell>{num(r.c2, 0)}</TableCell>
                  <TableCell>{num(r.c3, 0)}</TableCell>
                  <TableCell>{num(r.c4, 0)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-start gap-2">
                      {card ? (
                        <Link href={`/theses/${card.id}`}>Open card</Link>
                      ) : (
                        <form action={research}>
                          <input type="hidden" name="company_id" value={r.company_id} />
                          <input type="hidden" name="week_end" value={r.week_end} />
                          <input type="hidden" name="back" value={back} />
                          <Button type="submit" size="sm">
                            Research
                          </Button>
                        </form>
                      )}
                      {gone ? (
                        <Badge variant="secondary">dismissed</Badge>
                      ) : (
                        <details>
                          <summary className="cursor-pointer text-sm text-blue-800 underline">Dismiss</summary>
                          <form action={dismiss} className="mt-2 flex flex-col gap-2">
                            <input type="hidden" name="company_id" value={r.company_id} />
                            <input type="hidden" name="week_end" value={r.week_end} />
                            <input type="hidden" name="back" value={back} />
                            <Label htmlFor={`reason-${r.company_id}`}>Reason</Label>
                            <Input id={`reason-${r.company_id}`} name="reason" required className="w-48" />
                            <Button type="submit" size="sm" variant="outline">
                              Dismiss
                            </Button>
                          </form>
                        </details>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
