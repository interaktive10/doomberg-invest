import Link from "next/link";
import { notFound } from "next/navigation";
import { LineChartCard, type Row } from "@/components/charts";
import { Empty, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  company as getCompany,
  contextHistory,
  events,
  facts,
  fundamentals,
  insiders,
  ownership,
  signalTimeline,
  thesesOf,
} from "@/lib/data";
import { big, code, num, pct } from "@/lib/format";
import { series } from "@/lib/metrics";
import { UUID } from "@/lib/forms";
import { STATE_LABEL } from "@/lib/theses";

// BRIEF §6 Company: fundamentals charts (revenue, OPM, ROIC and incremental ROIC, CCR, shares, ND/EBITDA,
// RPO/backlog); signal timeline; verified facts with quotes and links; ownership and insiders; events; context
// (valuation percentile chart, reverse-DCF inputs and implied growth); thesis link.

function factValue(f: { value_num: number | null; value_low: number | null; value_high: number | null; unit: string }): string {
  const v = (x: number | null) => (x === null ? "n/a" : f.unit === "percent" ? `${num(x)}%` : big(x));
  const base = f.value_num !== null ? v(f.value_num) : f.value_low !== null || f.value_high !== null ? `${v(f.value_low)}–${v(f.value_high)}` : "";
  return f.unit === "percent" || f.unit === "usd" || f.unit === "inr" ? base : `${base} ${f.unit}`.trim();
}

function pctCell(v: unknown): string {
  return v === null || v === undefined ? "" : `${num(Number(v))}%`;
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const c = await getCompany(id);
  if (c === null) notFound();
  const [rows, own, ins, evs, fs, sigs, ctx, ths] = await Promise.all([
    fundamentals(id),
    ownership(id),
    insiders(id),
    events(id),
    facts([id], 30),
    signalTimeline(id),
    contextHistory(id),
    thesesOf(id),
  ]);
  const points = series(rows, c.market);
  const data: Row[] = points.map((p) => ({ ...p }));
  const weeks = new Map<string, string[]>();
  for (const s of sigs) weeks.set(s.week_end, [...(weeks.get(s.week_end) ?? []), s.signal_id]);
  const c1: Row[] = ctx.filter((x) => x.metric_id === "C1" && x.pct !== null).map((x) => ({ week: x.week_end, pct: Number(x.pct) / 100 }));
  const c2 = [...ctx].reverse().find((x) => x.metric_id === "C2");
  const currency = rows.find((r) => r.currency)?.currency ?? (c.market === "us" ? "USD" : "INR");
  return (
    <Page
      title={
        <>
          {c.name} <span className="text-gray-700">({code(c)})</span>
        </>
      }
    >
      <p className="text-sm text-gray-700">
        {c.market.toUpperCase()} · {c.sector ?? "sector n/a"} · {c.industry ?? "industry n/a"}
        {c.capex_desk ? " · Capex Desk" : ""}
        {c.in_universe ? "" : ` · outside the universe${c.excluded_reason ? ` (${c.excluded_reason})` : ""}`} · money in {currency}
      </p>
      <Section title="Thesis" id="thesis">
        {ths.length === 0 ? (
          <Empty>No thesis or card for this company.</Empty>
        ) : (
          <ul className="list-disc pl-5 text-sm">
            {ths.map((t) => (
              <li key={t.id}>
                <Link href={`/theses/${t.id}`}>
                  {STATE_LABEL[t.state]} · week {t.created_week} · {t.author}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Fundamentals (TTM)" id="fundamentals">
        {rows.length === 0 ? (
          <Empty>No fundamentals yet.</Empty>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <LineChartCard title="Revenue (TTM)" data={data} series={[{ key: "revenue", label: "Revenue" }]} format="big" />
            <LineChartCard title="Operating margin (TTM)" data={data} series={[{ key: "opm", label: "OPM" }]} format="pct" />
            <LineChartCard
              title="ROIC and incremental ROIC"
              data={data}
              series={[
                { key: "roic", label: "ROIC" },
                { key: "incremental_roic", label: "Incremental ROIC" },
              ]}
              format="pct"
            />
            <LineChartCard title="Cash conversion (CFO / net income, TTM)" data={data} series={[{ key: "ccr", label: "CCR" }]} format="x" />
            <LineChartCard title="Diluted shares" data={data} series={[{ key: "shares", label: "Shares" }]} format="big" />
            <LineChartCard title="Net debt / EBITDA" data={data} series={[{ key: "nd_ebitda", label: "ND/EBITDA" }]} format="x" />
            <LineChartCard title="RPO / backlog" data={data} series={[{ key: "rpo", label: "RPO" }]} format="big" />
          </div>
        )}
      </Section>
      <Section title="Signal timeline (weeks a signal fired)" id="signals">
        {weeks.size === 0 ? (
          <Empty>No signal has fired.</Empty>
        ) : (
          <Table label="Signal timeline">
            <TableHeader>
              <TableRow>
                <TableHead>Week ending</TableHead>
                <TableHead>Fired</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...weeks.entries()].slice(0, 26).map(([w, ids]) => (
                <TableRow key={w}>
                  <TableCell>{w}</TableCell>
                  <TableCell>
                    {ids.sort().map((s) => (
                      <Badge key={s} className="mr-1">
                        {s}
                      </Badge>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Verified facts" id="facts">
        {fs.length === 0 ? (
          <Empty>No verified text facts.</Empty>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {fs.map((f) => (
              <li key={f.id} className="rounded-md border border-gray-300 p-3">
                <div className="font-medium">
                  {f.fact_type} · {f.subject_key} · {factValue(f)}
                  {f.period_label ? ` · ${f.period_label}` : ""} · as of {f.as_of}
                </div>
                <blockquote className="mt-1 border-l-4 border-gray-300 pl-3 text-gray-900">“{f.quote}”</blockquote>
                {f.documents ? (
                  <a href={f.documents.url} rel="noreferrer" target="_blank" className="mt-1 inline-block">
                    {f.documents.kind} {f.documents.published_at.slice(0, 10)}
                    {f.documents.title ? `: ${f.documents.title}` : ""}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Ownership" id="ownership">
        {own.length === 0 ? (
          <Empty>No ownership data.</Empty>
        ) : (
          <Table label="Ownership">
            <TableHeader>
              <TableRow>
                <TableHead>Quarter</TableHead>
                <TableHead>Institutions</TableHead>
                <TableHead>FII</TableHead>
                <TableHead>DII</TableHead>
                <TableHead>Promoter</TableHead>
                <TableHead>Pledged</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {own.map((o) => (
                <TableRow key={`${str(o.quarter_end)}-${str(o.filed_at)}`}>
                  <TableCell>{str(o.quarter_end)}</TableCell>
                  <TableCell>{str(o.inst_holders)}</TableCell>
                  <TableCell>{pctCell(o.fii_pct)}</TableCell>
                  <TableCell>{pctCell(o.dii_pct)}</TableCell>
                  <TableCell>{pctCell(o.promoter_pct)}</TableCell>
                  <TableCell>{pctCell(o.promoter_pledged_pct)}</TableCell>
                  <TableCell>{str(o.source)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Insiders" id="insiders">
        {ins.length === 0 ? (
          <Empty>No insider events.</Empty>
        ) : (
          <Table label="Insider events">
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Person</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Shares</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Planned</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ins.map((e) => (
                <TableRow key={str(e.id)}>
                  <TableCell>{str(e.event_date)}</TableCell>
                  <TableCell>{str(e.person)}</TableCell>
                  <TableCell>{str(e.role)}</TableCell>
                  <TableCell>{str(e.kind)}</TableCell>
                  <TableCell>{big(e.shares as number | null)}</TableCell>
                  <TableCell>{big(e.value as number | null)}</TableCell>
                  <TableCell>{e.planned ? "yes" : "no"}</TableCell>
                  <TableCell>
                    {e.source_url ? (
                      <a href={str(e.source_url)} rel="noreferrer" target="_blank">
                        filing
                      </a>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Events" id="events">
        {evs.length === 0 ? (
          <Empty>No corporate events.</Empty>
        ) : (
          <Table label="Corporate events">
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {evs.map((e) => (
                <TableRow key={str(e.id)}>
                  <TableCell>{str(e.event_date)}</TableCell>
                  <TableCell>{str(e.kind)}</TableCell>
                  <TableCell className="max-w-md break-words">{str(e.detail)}</TableCell>
                  <TableCell>
                    {e.source_url ? (
                      <a href={str(e.source_url)} rel="noreferrer" target="_blank">
                        source
                      </a>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Context (uses price)" id="context">
        <div className="grid gap-4 md:grid-cols-2">
          <LineChartCard
            title="Valuation percentile vs own history (C1; high = expensive)"
            data={c1}
            series={[{ key: "pct", label: "Percentile" }]}
            format="pct"
            xKey="week"
          />
          <div className="rounded-lg border border-gray-300 p-3 text-sm">
            <h3 className="mb-2 font-semibold">Reverse DCF (C2)</h3>
            {c2 ? (
              <>
                <p>
                  Week {c2.week_end}: evidence growth minus implied growth = {pct(c2.value)}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
                  {Object.entries(c2.inputs).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-gray-700">{k}</dt>
                      <dd className="break-words">{str(v)}</dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <Empty>No reverse DCF yet (candidates only).</Empty>
            )}
          </div>
        </div>
      </Section>
    </Page>
  );
}
