import Link from "next/link";
import { FactItem } from "@/components/fact";
import { CapexGraph, type GraphData } from "@/components/graph";
import { Markdown } from "@/components/markdown";
import { Empty, Flash, Kpi, KpiRibbon, Page, Section } from "@/components/page";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { capexBriefs, capexDeskIds, capexIndex, facts, graphEdges, memberships, type Membership } from "@/lib/data";
import { code, num, pct } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { decideMembership } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Capex Desk" };

// BRIEF §6 Capex Desk: category demand indices; ledger facts; counterparty graph (Cytoscape); cross-border
// memberships (confirm/reject); brief archive.

function who(m: Membership): string {
  return m.companies ? `${m.companies.name} (${code(m.companies)})` : m.company_id;
}

export default async function Capex({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const [index, members, ids, edges, briefs] = await Promise.all([capexIndex(), memberships(), capexDeskIds(), graphEdges(400), capexBriefs()]);
  const ledger = await facts(ids, 40);
  const proposed = members.filter((m) => m.status === "proposed");
  const decided = members.filter((m) => m.status !== "proposed");
  const graph: GraphData = { nodes: [], edges: [] };
  const seen = new Set<string>();
  for (const e of edges) {
    const a = `c:${e.from_company_id}`;
    const b = `e:${e.to_entity_id}`;
    if (!seen.has(a)) {
      seen.add(a);
      graph.nodes.push({ id: a, label: e.companies?.name ?? "company", kind: "company" });
    }
    if (!seen.has(b)) {
      seen.add(b);
      graph.nodes.push({ id: b, label: e.entities?.name ?? "entity", kind: "entity" });
    }
    graph.edges.push({ id: `${a}>${b}:${e.relation}`, source: a, target: b, label: e.relation });
  }
  const rising = index.filter((r) => r.direction === "rising").length;
  const falling = index.filter((r) => r.direction === "falling").length;
  return (
    <Page title="Capex Desk" description="Capex demand by category, the counterparty graph and the verified facts behind them. A new membership counts only once you confirm it.">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <KpiRibbon>
        <Kpi label="Categories" value={index.length} />
        <Kpi label="Rising" value={rising} tone={rising > 0 ? "up" : undefined} />
        <Kpi label="Falling" value={falling} tone={falling > 0 ? "down" : undefined} />
        <Kpi label="Waiting for your decision" value={proposed.length} href="#memberships" tone={proposed.length > 0 ? "warn" : undefined} />
      </KpiRibbon>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12 xl:items-start">
        <Section
          title="Demand index by category"
          id="index"
          description="Each input's YoY change, z-scored and averaged per category: rising at +0.5σ or more, falling at −0.5σ or less."
          className="xl:col-span-7"
        >
          {index.length === 0 ? (
            <Empty>No index yet: the weekly capex job computes it from verified facts and EIA data.</Empty>
          ) : (
            <Table label="Demand index">
              <TableHeader>
                <TableRow>
                  <TableHead>Category</TableHead>
                  <TableHead>Week</TableHead>
                  <TableHead num>Index (z)</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead num>Input growth (YoY)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {index.map((r) => (
                  <TableRow key={r.category}>
                    <TableCell className="font-medium">{humanize(r.category)}</TableCell>
                    <TableCell className="num whitespace-nowrap">{r.week_end}</TableCell>
                    <TableCell
                      num
                      className={cn(r.value !== null && r.value > 0 ? "text-up" : r.value !== null && r.value < 0 ? "text-down" : undefined)}
                    >
                      {num(r.value, 2)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={r.direction === "rising" ? "success" : r.direction === "falling" ? "destructive" : "secondary"}>{r.direction}</Badge>
                    </TableCell>
                    <TableCell num>{pct(r.input_growth)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>

        <Section
          title={`Memberships waiting for a decision (${proposed.length})`}
          id="memberships"
          description="S11 counts a company in a category only once you confirm it."
          className="xl:col-span-5"
        >
          {proposed.length === 0 ? (
            <Empty>Nothing to confirm.</Empty>
          ) : (
            <ul className="flex flex-col gap-3">
              {proposed.map((m) => (
                <li key={`${m.company_id}:${m.category}`} className="rounded-sm border border-line bg-canvas p-3 text-[13px] sm:p-4">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Link href={`/company/${m.company_id}`} className="link-quiet">
                      {who(m)}
                    </Link>
                    <span aria-hidden="true" className="text-muted">
                      →
                    </span>
                    <span className="font-medium">{humanize(m.category)}</span>
                    <Badge variant="secondary">{m.source === "p06" ? "P-06 (cross-border)" : "industry map"}</Badge>
                  </div>
                  <p className="mt-2">{m.evidence}</p>
                  {m.quote ? <blockquote className="mt-2 border-l-2 border-line-strong pl-3 text-fg">“{m.quote}”</blockquote> : null}
                  <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-3 border-t border-line pt-3">
                    <form action={decideMembership}>
                      <input type="hidden" name="company_id" value={m.company_id} />
                      <input type="hidden" name="category" value={m.category} />
                      <input type="hidden" name="decision" value="confirm" />
                      <SubmitButton size="sm" aria-label={`Confirm ${who(m)} in ${humanize(m.category)}`}>
                        Confirm
                      </SubmitButton>
                    </form>
                    <form action={decideMembership} className="flex flex-wrap items-end gap-2">
                      <input type="hidden" name="company_id" value={m.company_id} />
                      <input type="hidden" name="category" value={m.category} />
                      <input type="hidden" name="decision" value="reject" />
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor={`rej-${m.company_id}-${m.category}`} className="text-xs">
                          Reason to reject
                        </Label>
                        <Input id={`rej-${m.company_id}-${m.category}`} name="reason" required className="w-56 max-w-full" />
                      </div>
                      <SubmitButton size="sm" variant="outline" aria-label={`Reject ${who(m)} in ${humanize(m.category)}`}>
                        Reject
                      </SubmitButton>
                    </form>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {decided.length > 0 ? (
            <details className="mt-4">
              <summary className="text-[13px] font-medium">Decided ({decided.length})</summary>
              <div className="mt-2">
                <Table label="Decided memberships">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Company</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {decided.map((m) => (
                      <TableRow key={`${m.company_id}:${m.category}`}>
                        <TableCell>{who(m)}</TableCell>
                        <TableCell>{humanize(m.category)}</TableCell>
                        <TableCell>
                          <Badge variant={m.status === "confirmed" ? "success" : "secondary"}>{m.status}</Badge>
                        </TableCell>
                        <TableCell>{m.decision_reason ?? ""}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </details>
          ) : null}
        </Section>

        <Section
          title="Counterparty graph"
          id="graph"
          description="Capex Desk companies (blue) and their counterparties from the ledger (grey)."
          className="xl:col-span-12"
        >
          {graph.edges.length === 0 ? (
            <Empty>No counterparty links yet.</Empty>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <CapexGraph data={graph} />
              <Table label="Counterparty links">
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead>Relation</TableHead>
                    <TableHead>Counterparty</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {edges.map((e) => (
                    <TableRow key={`${e.from_company_id}:${e.to_entity_id}:${e.relation}`}>
                      <TableCell>
                        <Link href={`/company/${e.from_company_id}`} className="link-quiet">
                          {e.companies?.name ?? "company"}
                        </Link>
                      </TableCell>
                      <TableCell>{humanize(e.relation)}</TableCell>
                      <TableCell>
                        {e.entities?.name ?? ""} <span className="text-xs text-muted">({e.entities?.kind ?? ""})</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Section>

        <Section title="Ledger facts" id="ledger" description="Verified facts about Capex Desk companies, newest first." className="xl:col-span-7">
          {ledger.length === 0 ? (
            <Empty>No verified facts yet.</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {ledger.map((f) => (
                <FactItem key={f.id} f={f} company />
              ))}
            </ul>
          )}
        </Section>

        <Section title="Capex brief archive" id="briefs" className="xl:col-span-5">
          {briefs.length === 0 ? (
            <Empty>No briefs yet.</Empty>
          ) : (
            <div className="flex flex-col gap-2">
              {briefs.map((b, i) => (
                <details key={b.week_end} open={i === 0} className="rounded-sm border border-line bg-canvas p-3 sm:p-4">
                  <summary className="text-[13px] font-medium">
                    Week ending <span className="num">{b.week_end}</span>
                  </summary>
                  <div className="mt-2">
                    <Markdown text={b.body_md} />
                  </div>
                </details>
              ))}
            </div>
          )}
        </Section>
      </div>
    </Page>
  );
}
