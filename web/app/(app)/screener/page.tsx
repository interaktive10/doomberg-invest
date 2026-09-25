import Link from "next/link";
import { Empty, Flash, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { screen, screens } from "@/lib/data";
import { code, num, pct } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { BUCKETS, FAMILIES, METRICS, SIGNALS, specFromForm, specToQuery, type ScreenSpec } from "@/lib/screener";
import { deleteScreen, saveScreen } from "./actions";

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

export default async function Screener({ searchParams }: { searchParams: Promise<Query> }) {
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
  return (
    <Page title="Screener">
      <Flash error={one(q, "error") ?? problem} ok={one(q, "ok")} />
      <Section title="Saved screens" id="saved">
        {saved.length === 0 ? (
          <Empty>No saved screens.</Empty>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {saved.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2">
                <Link href={`/screener?screen=${s.id}`}>{s.name}</Link>
                {chosen?.id === s.id ? <Badge variant="secondary">loaded</Badge> : null}
                <form action={deleteScreen}>
                  <input type="hidden" name="screen_id" value={s.id} />
                  <Button type="submit" variant="ghost" size="sm" aria-label={`Delete saved screen ${s.name}`}>
                    Delete
                  </Button>
                </form>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Filters" id="filters">
        <form method="get" action="/screener" className="grid gap-3 md:grid-cols-3">
          <input type="hidden" name="run" value="1" />
          <div className="flex flex-col gap-1">
            <Label htmlFor="s-market">Market</Label>
            <Select id="s-market" name="market" defaultValue={d.get("market") ?? ""}>
              <option value="">All</option>
              <option value="us">US</option>
              <option value="in">India</option>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="s-desk">Capex Desk</Label>
            <Select id="s-desk" name="capex_desk" defaultValue={d.get("capex_desk") ?? ""}>
              <option value="">All</option>
              <option value="true">Desk only</option>
              <option value="false">Not the desk</option>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="s-sector">Sector (exact)</Label>
            <Input id="s-sector" name="sector" defaultValue={d.get("sector") ?? ""} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="s-ev">Min Evidence (0–100)</Label>
            <Input id="s-ev" name="min_evidence" type="number" min="0" max="100" step="any" defaultValue={d.get("min_evidence") ?? ""} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="s-gap">Min Gap (0–100)</Label>
            <Input id="s-gap" name="min_gap" type="number" min="0" max="100" step="any" defaultValue={d.get("min_gap") ?? ""} />
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input id="s-hard" type="checkbox" name="exclude_hard_flags" defaultChecked={d.get("exclude_hard_flags") === "on"} />
            <Label htmlFor="s-hard">Exclude hard red flags</Label>
          </div>
          <fieldset className="md:col-span-3">
            <legend className="text-sm font-medium">Buckets</legend>
            <div className="mt-1 flex flex-wrap gap-3 text-sm">
              {BUCKETS.map((b) => (
                <label key={b} className="flex items-center gap-1">
                  <input type="checkbox" name="buckets" value={b} defaultChecked={has("buckets", b)} /> {b}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="md:col-span-3">
            <legend className="text-sm font-medium">Any of these signals fired</legend>
            <div className="mt-1 flex flex-wrap gap-3 text-sm">
              {SIGNALS.map((s) => (
                <label key={s} className="flex items-center gap-1">
                  <input type="checkbox" name="signals_any" value={s} defaultChecked={has("signals_any", s)} /> {s}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="md:col-span-3">
            <legend className="text-sm font-medium">All of these families</legend>
            <div className="mt-1 flex flex-wrap gap-3 text-sm">
              {FAMILIES.map((f) => (
                <label key={f} className="flex items-center gap-1">
                  <input type="checkbox" name="families_all" value={f} defaultChecked={has("families_all", f)} /> {f}
                </label>
              ))}
            </div>
          </fieldset>
          {[0, 1, 2].map((i) => (
            <fieldset key={i} className="flex flex-wrap items-end gap-2">
              <legend className="text-sm font-medium">Metric filter {i + 1}</legend>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`m-${i}`}>Metric</Label>
                <Select id={`m-${i}`} name={`metric_${i}`} defaultValue={d.get(`metric_${i}`) ?? ""}>
                  <option value="">none</option>
                  {METRICS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`o-${i}`}>Operator</Label>
                <Select id={`o-${i}`} name={`op_${i}`} defaultValue={d.get(`op_${i}`) ?? ">="}>
                  {[">=", "<=", ">", "<"].map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`v-${i}`}>Value</Label>
                <Input id={`v-${i}`} name={`value_${i}`} type="number" step="any" className="w-28" defaultValue={d.get(`value_${i}`) ?? ""} />
              </div>
            </fieldset>
          ))}
          <div className="flex items-end md:col-span-3">
            <Button type="submit">Run screen</Button>
          </div>
        </form>
      </Section>
      {run && spec ? (
        <Section title={`Results (${rows.length})`} id="results">
          <div className="mb-3 flex flex-wrap items-end gap-3">
            <a href={`/screener/export?${query}`} className="text-sm">
              Export CSV
            </a>
            <form action={saveScreen} className="flex flex-wrap items-end gap-2">
              <input type="hidden" name="spec" value={JSON.stringify(spec)} />
              <input type="hidden" name="query" value={query} />
              <div className="flex flex-col gap-1">
                <Label htmlFor="save-name">Save as</Label>
                <Input id="save-name" name="name" required defaultValue={chosen?.name ?? ""} className="w-48" />
              </div>
              <Button type="submit" variant="outline">
                Save screen
              </Button>
            </form>
          </div>
          {rows.length === 0 ? (
            <Empty>No company passes these filters.</Empty>
          ) : (
            <Table label="Screen results">
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>Sector</TableHead>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Evidence</TableHead>
                  <TableHead>Gap</TableHead>
                  <TableHead>Signals</TableHead>
                  <TableHead>Red flags</TableHead>
                  <TableHead>Revenue YoY</TableHead>
                  <TableHead>ROIC</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.company_id}>
                    <TableCell>
                      <Link href={`/company/${r.company_id}`}>{r.name}</Link> <span className="text-gray-700">({code(r)})</span>
                    </TableCell>
                    <TableCell>{r.market.toUpperCase()}</TableCell>
                    <TableCell>{r.sector ?? ""}</TableCell>
                    <TableCell>{r.bucket}</TableCell>
                    <TableCell>{num(r.evidence)}</TableCell>
                    <TableCell>{num(r.gap)}</TableCell>
                    <TableCell>{r.fired_signals.join(" ")}</TableCell>
                    <TableCell>{r.red_flags.join(" ")}</TableCell>
                    <TableCell>{pct(r.metrics.revenue_yoy)}</TableCell>
                    <TableCell>{pct(r.metrics.roic)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      ) : null}
    </Page>
  );
}
