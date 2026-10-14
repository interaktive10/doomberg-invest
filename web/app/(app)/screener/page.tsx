import Link from "next/link";
import { Empty, Flash, Kpi, KpiRibbon, Page, Section } from "@/components/page";
import { FlagBadges, ScoreBar, SignalBadges } from "@/components/score";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { choiceChip, Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { screen, screens } from "@/lib/data";
import { code, pct } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { BUCKET_LABEL, FAMILY_LABEL, label, METRIC_LABEL, SIGNAL_NAME } from "@/lib/labels";
import { BUCKETS, FAMILIES, METRICS, SIGNALS, specFromForm, specToQuery, type ScreenSpec } from "@/lib/screener";
import { cn } from "@/lib/utils";
import { deleteScreen, saveScreen } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Screener" };

// BRIEF §6 Screener: a filter builder over fundamentals, signals and context (the screen(spec) RPC, M4), saved screens
// and a CSV export (personal use).

function toParams(q: Query): URLSearchParams {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (k === "error" || k === "ok" || k === "screen" || k === "run") continue;
    for (const x of Array.isArray(v) ? v : v === undefined ? [] : [v]) p.append(k, x);
  }
  return p;
}

/** A checkbox that reads as a toggle chip (the box stays visible for keyboard and screen-reader users). */
function Chip({ name, value, checked, children, title }: { name: string; value: string; checked: boolean; children: React.ReactNode; title?: string }) {
  return (
    <label title={title} className={choiceChip}>
      <input type="checkbox" name={name} value={value} defaultChecked={checked} />
      {children}
    </label>
  );
}

export default async function Screener({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const saved = await screens();
  const chosen = saved.find((s) => s.id === one(q, "screen"));
  let spec: ScreenSpec | null = null;
  let problem: string | undefined;
  const params = toParams(q);
  try {
    spec = chosen && [...params.keys()].length === 0 ? chosen.spec : specFromForm(params);
  } catch {
    problem = "Some filter values are outside the allowed range.";
  }
  const run = spec !== null && (one(q, "run") === "1" || chosen !== undefined || [...params.keys()].length > 0);
  const rows = run && spec ? await screen({ limit: 500, ...spec }) : [];
  const query = spec ? specToQuery(spec).toString() : "";
  const d = spec ? specToQuery(spec) : new URLSearchParams();
  const has = (k: string, v: string) => d.getAll(k).includes(v);
  const counted = (n: number) => (run ? n : "–");
  return (
    <Page title="Screener" description="Filter the latest scored week by market, scores, signals, families and metrics. Save a screen to rerun it.">
      <Flash error={one(q, "error") ?? problem} ok={one(q, "ok")} />
      <KpiRibbon>
        <Kpi label="Saved screens" value={saved.length} />
        <Kpi label="Companies found" value={counted(rows.length)} hint={run ? "latest scored week" : "press Run screen"} />
        <Kpi label="In the Candidate bucket" value={counted(rows.filter((r) => r.bucket === "candidate").length)} />
        <Kpi
          label="With a hard red flag"
          value={counted(rows.filter((r) => r.hard_flag).length)}
          tone={rows.some((r) => r.hard_flag) ? "down" : undefined}
        />
      </KpiRibbon>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[22rem_minmax(0,1fr)] lg:items-start">
        <div className="flex min-w-0 flex-col gap-3">
          <Section title="Saved screens" id="saved">
            {saved.length === 0 ? (
              <Empty>No saved screens. Run a screen, then save it from the results.</Empty>
            ) : (
              <ul className="flex flex-wrap gap-2 text-[13px]">
                {saved.map((s) => (
                  <li
                    key={s.id}
                    className={cn(
                      "flex items-center gap-1 rounded-sm border py-0.5 pr-0.5 pl-3",
                      chosen?.id === s.id ? "border-accent bg-accent/10" : "border-line bg-raised",
                    )}
                  >
                    <Link href={`/screener?screen=${s.id}`} className="link-quiet">
                      {s.name}
                    </Link>
                    {chosen?.id === s.id ? <Badge variant="secondary">loaded</Badge> : null}
                    <form action={deleteScreen}>
                      <input type="hidden" name="screen_id" value={s.id} />
                      <SubmitButton variant="ghost" size="xs" aria-label={`Delete saved screen ${s.name}`}>
                        Delete
                      </SubmitButton>
                    </form>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Filters" id="filters">
            <form method="get" action="/screener" className="grid grid-cols-1 gap-5">
              <input type="hidden" name="run" value="1" />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <div className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor="s-market">Market</Label>
                  <Select id="s-market" name="market" defaultValue={d.get("market") ?? ""}>
                    <option value="">All</option>
                    <option value="us">US</option>
                    <option value="in">India</option>
                  </Select>
                </div>
                <div className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor="s-desk">Capex Desk</Label>
                  <Select id="s-desk" name="capex_desk" defaultValue={d.get("capex_desk") ?? ""}>
                    <option value="">All</option>
                    <option value="true">Desk only</option>
                    <option value="false">Not the desk</option>
                  </Select>
                </div>
                <div className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor="s-sector">Sector (exact)</Label>
                  <Input id="s-sector" name="sector" defaultValue={d.get("sector") ?? ""} placeholder="e.g. Industrials" />
                </div>
                <div className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor="s-ev">Min Evidence (0–100)</Label>
                  <Input id="s-ev" name="min_evidence" type="number" min="0" max="100" step="any" defaultValue={d.get("min_evidence") ?? ""} />
                </div>
                <div className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor="s-gap">Min Gap (0–100)</Label>
                  <Input id="s-gap" name="min_gap" type="number" min="0" max="100" step="any" defaultValue={d.get("min_gap") ?? ""} />
                </div>
                <div className="flex items-center gap-2 sm:pt-6 lg:pt-0">
                  <input id="s-hard" type="checkbox" name="exclude_hard_flags" defaultChecked={d.get("exclude_hard_flags") === "on"} />
                  <Label htmlFor="s-hard" className="font-normal">
                    Exclude hard red flags
                  </Label>
                </div>
              </div>
              <fieldset className="min-w-0">
                <legend className="mb-2 text-xs font-medium text-muted">Buckets</legend>
                <div className="flex flex-wrap gap-2">
                  {BUCKETS.map((b) => (
                    <Chip key={b} name="buckets" value={b} checked={has("buckets", b)}>
                      {label(BUCKET_LABEL, b)}
                    </Chip>
                  ))}
                </div>
              </fieldset>
              <fieldset className="min-w-0">
                <legend className="mb-2 text-xs font-medium text-muted">Any of these signals fired</legend>
                <div className="flex flex-wrap gap-2">
                  {SIGNALS.map((s) => (
                    <Chip key={s} name="signals_any" value={s} checked={has("signals_any", s)} title={SIGNAL_NAME[s]}>
                      {s}
                    </Chip>
                  ))}
                </div>
              </fieldset>
              <fieldset className="min-w-0">
                <legend className="mb-2 text-xs font-medium text-muted">All of these families</legend>
                <div className="flex flex-wrap gap-2">
                  {FAMILIES.map((f) => (
                    <Chip key={f} name="families_all" value={f} checked={has("families_all", f)}>
                      {FAMILY_LABEL[f]}
                    </Chip>
                  ))}
                </div>
              </fieldset>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-1">
                {[0, 1, 2].map((i) => (
                  <fieldset key={i} className="min-w-0 rounded-sm border border-line p-3">
                    <legend className="px-1 text-xs font-medium text-muted">Metric filter {i + 1}</legend>
                    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                      <div className="col-span-2 flex min-w-0 flex-col gap-1.5">
                        <Label htmlFor={`m-${i}`}>Metric</Label>
                        <Select id={`m-${i}`} name={`metric_${i}`} defaultValue={d.get(`metric_${i}`) ?? ""} className="w-full min-w-0">
                          <option value="">none</option>
                          {METRICS.map((m) => (
                            <option key={m} value={m}>
                              {METRIC_LABEL[m] ?? m}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div className="flex min-w-0 flex-col gap-1.5">
                        <Label htmlFor={`o-${i}`}>Operator</Label>
                        <Select id={`o-${i}`} name={`op_${i}`} defaultValue={d.get(`op_${i}`) ?? ">="}>
                          {[">=", "<=", ">", "<"].map((o) => (
                            <option key={o} value={o}>
                              {o}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div className="flex min-w-0 flex-col gap-1.5">
                        <Label htmlFor={`v-${i}`}>Value</Label>
                        <Input id={`v-${i}`} name={`value_${i}`} type="number" step="any" className="w-28" defaultValue={d.get(`value_${i}`) ?? ""} />
                      </div>
                    </div>
                  </fieldset>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit">Run screen</Button>
                <Link href="/screener" className="text-[13px]">
                  Reset
                </Link>
              </div>
            </form>
          </Section>
        </div>
        {run && spec ? (
          <Section
            title={`Results (${rows.length})`}
            id="results"
            actions={
              <>
                <a href={`/screener/export?${query}`} className={buttonVariants({ variant: "outline", size: "sm" })} download>
                  Export CSV
                </a>
                <form action={saveScreen} className="flex items-end gap-2">
                  <input type="hidden" name="spec" value={JSON.stringify(spec)} />
                  <input type="hidden" name="query" value={query} />
                  <Label htmlFor="save-name" className="sr-only sm:not-sr-only sm:self-center">
                    Save as
                  </Label>
                  <Input id="save-name" name="name" required defaultValue={chosen?.name ?? ""} placeholder="Screen name" className="h-8 w-40" />
                  <SubmitButton variant="outline" size="sm">
                    Save screen
                  </SubmitButton>
                </form>
              </>
            }
          >
            {rows.length === 0 ? (
              <Empty>No company passes these filters.</Empty>
            ) : (
              <Table label="Screen results">
                <TableHeader>
                  <TableRow>
                    <TableHead sticky>Company</TableHead>
                    <TableHead>Market</TableHead>
                    <TableHead>Sector</TableHead>
                    <TableHead>Bucket</TableHead>
                    <TableHead num>Evidence</TableHead>
                    <TableHead num>Gap</TableHead>
                    <TableHead>Signals</TableHead>
                    <TableHead>Red flags</TableHead>
                    <TableHead num>Revenue YoY</TableHead>
                    <TableHead num>ROIC</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.company_id}>
                      <TableCell sticky className="min-w-44">
                        <Link href={`/company/${r.company_id}`} className="link-quiet">
                          {r.name}
                        </Link>{" "}
                        <span className="font-mono text-xs text-muted">({code(r)})</span>
                      </TableCell>
                      <TableCell>{r.market.toUpperCase()}</TableCell>
                      <TableCell className="whitespace-nowrap">{r.sector ?? ""}</TableCell>
                      <TableCell>
                        <Badge variant={r.bucket === "candidate" ? "success" : r.bucket === "excluded" ? "destructive" : "secondary"}>
                          {label(BUCKET_LABEL, r.bucket)}
                        </Badge>
                      </TableCell>
                      <TableCell num>
                        <ScoreBar value={r.evidence} />
                      </TableCell>
                      <TableCell num>
                        <ScoreBar value={r.gap} />
                      </TableCell>
                      <TableCell>
                        <SignalBadges ids={r.fired_signals} />
                      </TableCell>
                      <TableCell>
                        <FlagBadges ids={r.red_flags} hard={r.hard_flag} />
                      </TableCell>
                      <TableCell num>{pct(r.metrics.revenue_yoy)}</TableCell>
                      <TableCell num>{pct(r.metrics.roic)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>
        ) : (
          <Empty>Set filters and press Run screen.</Empty>
        )}
      </div>
    </Page>
  );
}
