import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChartGrid, LineChartCard, type Row } from "@/components/charts";
import { FactItem } from "@/components/fact";
import { Empty, Kpi, KpiRibbon, Page, Section } from "@/components/page";
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
import { cn } from "@/lib/utils";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Company: fundamentals charts (revenue, OPM, ROIC and incremental ROIC, CCR, shares, ND/EBITDA,
// RPO/backlog; the weekly run's company_series, §4.6 definitions); signal timeline; verified facts with quotes and links; ownership and insiders; events; context
// (valuation percentile chart, reverse-DCF inputs and implied growth); thesis link. The ribbon on top: the latest
// scored week's two scores, bucket and signals.

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
  const firedNow = score ? (weeks.get(score.week_end) ?? []).length : 0;
  return (
    <Page
      title={
        <>
          {c.name} <span className="font-mono font-normal text-muted">({code(c)})</span>
        </>
      }
      description={
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">{c.market === "us" ? "US" : "India"}</Badge>
          {c.sector ? <Badge variant="outline">{c.sector}</Badge> : null}
          {c.industry ? <Badge variant="outline">{c.industry}</Badge> : null}
          {c.capex_desk ? <Badge>Capex Desk</Badge> : null}
          {c.in_universe ? null : <Badge variant="warning">outside the universe{c.excluded_reason ? `: ${c.excluded_reason}` : ""}</Badge>}
          <span className="text-xs text-muted">money in {currency}</span>
        </div>
      }
    >
      {score ? (
        <KpiRibbon>
          <Kpi label="Strength of evidence" value={num(score.evidence)} bar={score.evidence} hint="0–100, never uses price" />
          <Kpi label="Not priced in yet" value={num(score.gap)} bar={score.gap} hint="0–100, uses price" />
          <Kpi
            label="Bucket"
            value={label(BUCKET_LABEL, score.bucket)}
            tone={score.bucket === "candidate" ? "up" : score.bucket === "excluded" ? "down" : undefined}
            hint={`week ending ${score.week_end}`}
          />
          <Kpi label="Signals fired this week" value={firedNow} />
          <Kpi
            label="Signal families"
            value={
              <span className="block font-sans text-sm font-normal tracking-normal">
                <FamilyBadges ids={score.families} />
              </span>
            }
          />
        </KpiRibbon>
      ) : null}
      <nav
        aria-label="On this page"
        className="z-20 -mx-4 flex overflow-x-auto border-b border-line bg-canvas/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:sticky lg:top-12"
      >
        {SECTIONS.map(([hash, name]) => (
          <a
            key={hash}
            href={`#${hash}`}
            className="inline-flex h-10 items-center px-3 text-[13px] font-medium whitespace-nowrap text-muted no-underline hover:text-fg focus-visible:outline-offset-[-2px]"
          >
            {name}
          </a>
        ))}
      </nav>
      <Section title="Thesis" id="thesis">
        {ths.length === 0 ? (
          <Empty>No thesis or card for this company. Start one with Research on the Candidates screen.</Empty>
        ) : (
          <ul className="flex flex-wrap gap-2 text-[13px]">
            {ths.map((t) => (
              <li key={t.id}>
                <Link
                  href={`/theses/${t.id}`}
                  className="inline-flex rounded-sm border border-line bg-raised p-2.5 font-medium text-fg no-underline transition-colors hover:border-edge hover:text-fg"
                >
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
          <ChartGrid>
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
            <LineChartCard
              title="RPO / backlog"
              data={data}
              series={[{ key: "order_book", label: "Order book" }]}
              format="big"
              className="sm:col-span-2 xl:col-span-3"
            />
          </ChartGrid>
        )}
      </Section>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12 xl:items-start">
        <Section title="Signal timeline" id="signals" description="The weeks a signal fired, newest first." className="xl:col-span-5">
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
                    <TableCell className="num w-36 whitespace-nowrap">{w}</TableCell>
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
        <Section title="Verified facts" id="facts" description="Each one matched word for word in its document." className="xl:col-span-7">
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
        <Section title="Ownership" id="ownership" className="xl:col-span-5">
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
                    <TableCell className="num whitespace-nowrap">{str(o.quarter_end)}</TableCell>
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
        <Section title="Insiders" id="insiders" className="xl:col-span-7">
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
                    <TableCell className="num whitespace-nowrap">{str(e.event_date)}</TableCell>
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
        <Section title="Events" id="events" className="xl:col-span-12">
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
                    <TableCell className="num whitespace-nowrap">{str(e.event_date)}</TableCell>
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
        <Section
          title="Context (uses price)"
          id="context"
          description="Where the price stands against the evidence. Context never feeds the Evidence score."
          className="xl:col-span-12"
        >
          <ChartGrid className="md:grid-cols-2 xl:grid-cols-2">
            <LineChartCard
              title="Valuation percentile vs own history (C1; high = expensive)"
              data={c1}
              series={[{ key: "pct", label: "Percentile" }]}
              format="pct"
              xKey="week"
            />
            <div className="min-w-0 border-t border-l border-line bg-panel p-3 text-[13px]">
              <h3 className="mb-2 text-xs font-medium text-muted">Reverse DCF (C2)</h3>
              {c2 ? (
                <>
                  <p className="text-fg">
                    Week <span className="num">{c2.week_end}</span>: evidence growth minus implied growth ={" "}
                    <span
                      className={cn(
                        "num font-semibold",
                        c2.value !== null && c2.value > 0 ? "text-up" : c2.value !== null && c2.value < 0 ? "text-down" : undefined,
                      )}
                    >
                      {pct(c2.value)}
                    </span>
                  </p>
                  <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5">
                    {dcfRows(c2.inputs).map((r) => (
                      <div key={r.key} className="contents">
                        <dt className="text-muted">{r.label}</dt>
                        <dd className="num text-right break-words text-fg">{r.value}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              ) : (
                <Empty>No reverse DCF yet (candidates only).</Empty>
              )}
            </div>
          </ChartGrid>
        </Section>
      </div>
    </Page>
  );
}
