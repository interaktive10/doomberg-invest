import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChartGrid, LineChartCard, type Row } from "@/components/charts";
import { FactItem } from "@/components/fact";
import { Empty, Page, Section } from "@/components/page";
import { FamilyBadges } from "@/components/score";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { company as getCompany, companySeries, contextHistory, events, facts, fundamentals, insiders, latestScore, thesesOf } from "@/lib/data";
import { big, code, num, pct } from "@/lib/format";
import { BUCKET_LABEL, dcfRows, detailText, humanize, label } from "@/lib/labels";
import { chartRows } from "@/lib/metrics";
import { UUID } from "@/lib/forms";
import { STATE_LABEL } from "@/lib/theses";
import { cn } from "@/lib/utils";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Company: the latest scored week's two scores, bucket and families under the name; fundamentals charts
// (revenue, OPM, ROIC and incremental ROIC, CCR, shares, ND/EBITDA, RPO/backlog; the weekly run's company_series,
// §4.6 definitions); verified facts with quotes and links; insiders; events; the reverse DCF (C2); thesis link.
// Overhaul PR 4: no ribbon, no C1 chart, signal timeline or Ownership table (S8's inputs carry the holder counts),
// and a table with no rows is left out.

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

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
  const [rows, ins, evs, fs, ctx, ths, ser, score] = await Promise.all([
    fundamentals(id),
    insiders(id),
    events(id),
    facts([id], 30),
    contextHistory(id),
    thesesOf(id),
    companySeries(id),
    latestScore(id),
  ]);
  const data: Row[] = chartRows(ser?.points ?? []).map((p) => ({ ...p }));
  const c2 = [...ctx].reverse().find((x) => x.metric_id === "C2");
  const currency = rows.find((r) => r.currency)?.currency ?? (c.market === "us" ? "USD" : "INR");
  const sections: [id: string, name: string, shown: boolean][] = [
    ["thesis", "Thesis", true],
    ["fundamentals", "Fundamentals", true],
    ["facts", "Facts", fs.length > 0],
    ["insiders", "Insiders", ins.length > 0],
    ["events", "Events", evs.length > 0],
    ["context", "Context", c2 !== undefined],
  ];
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
          {c.in_universe ? null : <Badge variant="warning">outside the universe{c.excluded_reason ? `: ${c.excluded_reason}` : ""}</Badge>}
          <span className="text-xs text-muted">money in {currency}</span>
          {score ? (
            <span className="flex basis-full flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[13px]">
              <span>
                Strength of evidence <span className="num font-semibold text-fg">{num(score.evidence)}</span>
                <span className="text-xs"> (never uses price)</span>
              </span>
              <span>
                Not priced in yet <span className="num font-semibold text-fg">{num(score.gap)}</span>
                <span className="text-xs"> (uses price)</span>
              </span>
              <span className={score.bucket === "candidate" ? "text-up" : score.bucket === "excluded" ? "text-down" : "text-fg"}>
                {label(BUCKET_LABEL, score.bucket)}
              </span>
              <span className="num text-xs">week ending {score.week_end}</span>
              <FamilyBadges ids={score.families} />
            </span>
          ) : null}
        </div>
      }
    >
      <nav
        aria-label="On this page"
        className="z-20 -mx-4 flex overflow-x-auto border-b border-line bg-canvas/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:sticky lg:top-12"
      >
        {sections.filter(([, , shown]) => shown).map(([hash, name]) => (
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
      {fs.length > 0 ? (
        <Section title="Verified facts" id="facts" description="Each one matched word for word in its document.">
          <ul className="flex flex-col gap-2">
            {fs.map((f) => (
              <FactItem key={f.id} f={f} />
            ))}
          </ul>
        </Section>
      ) : null}
      {ins.length > 0 ? (
        <Section title="Insiders" id="insiders">
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
        </Section>
      ) : null}
      {evs.length > 0 ? (
        <Section title="Events" id="events">
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
        </Section>
      ) : null}
      {c2 ? (
        <Section
          title="Context (uses price)"
          id="context"
          description="Where the price stands against the evidence. Context never feeds the Evidence score."
        >
          <div className="max-w-xl text-[13px]">
            <h3 className="mb-2 text-xs font-medium text-muted">Reverse DCF (C2)</h3>
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
          </div>
        </Section>
      ) : null}
    </Page>
  );
}
