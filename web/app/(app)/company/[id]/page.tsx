import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { LineChartCard, type Row } from "@/components/charts";
import { FactItem } from "@/components/fact";
import { Empty, Page, Section, Stat } from "@/components/page";
import { FamilyBadges } from "@/components/score";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  company as getCompany,
  companySeries,
  contextHistory,
  events,
  facts,
  fundamentals,
  insiders,
  latestScore,
  ownership,
  signalTimeline,
  thesesOf,
} from "@/lib/data";
import { big, code, num, pct } from "@/lib/format";
import { BUCKET_LABEL, dcfRows, detailText, humanize, label, SIGNAL_NAME, sourceLabel } from "@/lib/labels";
import { chartRows } from "@/lib/metrics";
import { UUID } from "@/lib/forms";
import { STATE_LABEL } from "@/lib/theses";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Company: fundamentals charts (revenue, OPM, ROIC and incremental ROIC, CCR, shares, ND/EBITDA,
// RPO/backlog; the weekly run's company_series, §4.6 definitions); signal timeline; verified facts with quotes and links; ownership and insiders; events; context
// (valuation percentile chart, reverse-DCF inputs and implied growth); thesis link.

function pctCell(v: unknown): string {
  return v === null || v === undefined ? "" : `${num(Number(v))}%`;
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const OWNERSHIP: [key: string, head: string][] = [
  ["inst_holders", "Institutions"],
  ["fii_pct", "FII"],
  ["dii_pct", "DII"],
  ["promoter_pct", "Promoter"],
  ["promoter_pledged_pct", "Pledged"],
];

const SECTIONS: [id: string, name: string][] = [
  ["thesis", "Thesis"],
  ["fundamentals", "Fundamentals"],
  ["signals", "Signals"],
  ["facts", "Facts"],
  ["ownership", "Ownership"],
  ["insiders", "Insiders"],
  ["events", "Events"],
  ["context", "Context"],
];

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const c = UUID.test(id) ? await getCompany(id) : null;
  return { title: c ? `${c.name} (${code(c)})` : "Company" };
}

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const c = await getCompany(id);
  if (c === null) notFound();
  const [rows, own, ins, evs, fs, sigs, ctx, ths, ser, score] = await Promise.all([
    fundamentals(id),
    ownership(id),
    insiders(id),
    events(id),
    facts([id], 30),
    signalTimeline(id),
    contextHistory(id),
    thesesOf(id),
    companySeries(id),
    latestScore(id),
  ]);
  const data: Row[] = chartRows(ser?.points ?? []).map((p) => ({ ...p }));
  const weeks = new Map<string, string[]>();
  for (const s of sigs) weeks.set(s.week_end, [...(weeks.get(s.week_end) ?? []), s.signal_id]);
  const c1: Row[] = ctx.filter((x) => x.metric_id === "C1" && x.pct !== null).map((x) => ({ week: x.week_end, pct: Number(x.pct) / 100 }));
  const c2 = [...ctx].reverse().find((x) => x.metric_id === "C2");
  const currency = rows.find((r) => r.currency)?.currency ?? (c.market === "us" ? "USD" : "INR");
  const ownCols = OWNERSHIP.filter(([k]) => own.some((o) => o[k] !== null && o[k] !== undefined));
  return (
    <Page
      title={
        <>
          {c.name} <span className="font-normal text-gray-700">({code(c)})</span>
        </>
      }
      description={
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">{c.market === "us" ? "US" : "India"}</Badge>
          {c.sector ? <Badge variant="outline">{c.sector}</Badge> : null}
          {c.industry ? <Badge variant="outline">{c.industry}</Badge> : null}
          {c.capex_desk ? <Badge>Capex Desk</Badge> : null}
          {c.in_universe ? null : <Badge variant="warning">outside the universe{c.excluded_reason ? `: ${c.excluded_reason}` : ""}</Badge>}
          <span className="text-xs text-gray-700">money in {currency}</span>
        </div>
      }
    >
      {score ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Evidence" value={num(score.evidence)} hint="0–100; never uses price" />
          <Stat label="Gap" value={num(score.gap)} hint="0–100; C1–C4" />
          <Stat label="Bucket" value={label(BUCKET_LABEL, score.bucket)} hint={`week ending ${score.week_end}`} />
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <div className="text-xs font-medium tracking-wide text-gray-700 uppercase">Families</div>
            <div className="mt-2">
              <FamilyBadges ids={score.families} />
            </div>
          </div>
        </div>
      ) : null}
      <nav aria-label="On this page" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 text-sm whitespace-nowrap">
        {SECTIONS.map(([hash, name]) => (
          <a key={hash} href={`#${hash}`} className="rounded-md px-2.5 py-1 font-medium text-gray-700 no-underline hover:bg-gray-200 hover:text-gray-900">
            {name}
          </a>
        ))}
      </nav>
      <Section title="Thesis" id="thesis">
        {ths.length === 0 ? (
          <Empty>No thesis or card for this company. Start one with Research on the Candidates screen.</Empty>
        ) : (
          <ul className="flex flex-wrap gap-2 text-sm">
            {ths.map((t) => (
              <li key={t.id}>
                <Link href={`/theses/${t.id}`} className="inline-flex rounded-lg border border-gray-200 px-3 py-1.5 font-medium no-underline hover:border-blue-300 hover:bg-blue-50">
                  {STATE_LABEL[t.state]} · week {t.created_week} · {t.author}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section
        title="Fundamentals (TTM)"
        id="fundamentals"
        description={data.length > 0 ? `As of the week scored ${ser?.week_end}, with the signals' definitions (BRIEF §4.6).` : undefined}
      >
        {data.length === 0 ? (
          <Empty>No chart series yet: the weekly scoring run computes them.</Empty>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
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
            <LineChartCard title="RPO / backlog" data={data} series={[{ key: "order_book", label: "Order book" }]} format="big" />
          </div>
        )}
      </Section>
      <Section title="Signal timeline" id="signals" description="The weeks a signal fired, newest first.">
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
                  <TableCell className="w-36 whitespace-nowrap tabular-nums">{w}</TableCell>
                  <TableCell>
                    <span className="flex flex-wrap gap-1">
                      {ids.sort((a, b) => a.localeCompare(b, "en", { numeric: true })).map((s) => (
                        <Badge key={s} title={SIGNAL_NAME[s] ?? s}>
                          {s} <span className="font-normal">{SIGNAL_NAME[s] ?? ""}</span>
                        </Badge>
                      ))}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Verified facts" id="facts" description="Each one matched word for word in its document.">
        {fs.length === 0 ? (
          <Empty>No verified text facts.</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {fs.map((f) => (
              <FactItem key={f.id} f={f} />
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
                {ownCols.map(([k, head]) => (
                  <TableHead key={k} num>
                    {head}
                  </TableHead>
                ))}
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {own.map((o) => (
                <TableRow key={`${str(o.quarter_end)}-${str(o.filed_at)}`}>
                  <TableCell className="whitespace-nowrap tabular-nums">{str(o.quarter_end)}</TableCell>
                  {ownCols.map(([k]) => (
                    <TableCell key={k} num>
                      {k === "inst_holders" ? (o[k] === null || o[k] === undefined ? "" : Number(o[k]).toLocaleString("en-US")) : pctCell(o[k])}
                    </TableCell>
                  ))}
                  <TableCell>{sourceLabel(str(o.source))}</TableCell>
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
                <TableHead num>Shares</TableHead>
                <TableHead num>Value</TableHead>
                <TableHead>Planned</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ins.map((e) => (
                <TableRow key={str(e.id)}>
                  <TableCell className="whitespace-nowrap tabular-nums">{str(e.event_date)}</TableCell>
                  <TableCell>{str(e.person)}</TableCell>
                  <TableCell>{str(e.role)}</TableCell>
                  <TableCell>{humanize(str(e.kind))}</TableCell>
                  <TableCell num>{big(e.shares as number | null)}</TableCell>
                  <TableCell num>
                    {big(e.value as number | null)} {e.value === null || e.value === undefined ? "" : str(e.currency).toUpperCase()}
                  </TableCell>
                  <TableCell>{e.planned ? "yes" : "no"}</TableCell>
                  <TableCell>
                    {e.source_url ? (
                      <a href={str(e.source_url)} rel="noreferrer" target="_blank">
                        filing<span className="sr-only"> (opens in a new tab)</span>
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
                  <TableCell className="whitespace-nowrap tabular-nums">{str(e.event_date)}</TableCell>
                  <TableCell className="whitespace-nowrap">{humanize(str(e.kind))}</TableCell>
                  <TableCell className="max-w-md break-words">{detailText(e.detail)}</TableCell>
                  <TableCell>
                    {e.source_url ? (
                      <a href={str(e.source_url)} rel="noreferrer" target="_blank">
                        source<span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Context (uses price)" id="context" description="Where the price stands against the evidence. Context never feeds the Evidence score.">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <LineChartCard
            title="Valuation percentile vs own history (C1; high = expensive)"
            data={c1}
            series={[{ key: "pct", label: "Percentile" }]}
            format="pct"
            xKey="week"
          />
          <div className="rounded-lg border border-gray-200 p-3 text-sm">
            <h3 className="mb-2 text-sm font-semibold">Reverse DCF (C2)</h3>
            {c2 ? (
              <>
                <p className="text-gray-900">
                  Week {c2.week_end}: evidence growth minus implied growth ={" "}
                  <span className="font-semibold tabular-nums">{pct(c2.value)}</span>
                </p>
                <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5">
                  {dcfRows(c2.inputs).map((r) => (
                    <div key={r.key} className="contents">
                      <dt className="text-gray-700">{r.label}</dt>
                      <dd className="text-right break-words text-gray-900 tabular-nums">{r.value}</dd>
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
