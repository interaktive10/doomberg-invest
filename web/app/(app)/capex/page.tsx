import Link from "next/link";
import { CapexGraph, type GraphData } from "@/components/graph";
import { Markdown } from "@/components/markdown";
import { Empty, Flash, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { capexBriefs, capexDeskIds, capexIndex, facts, graphEdges, memberships, type Membership } from "@/lib/data";
import { big, code, num, pct } from "@/lib/format";
import { one, type Query } from "@/lib/forms";
import { decideMembership } from "./actions";

// BRIEF §6 Capex Desk: category demand indices; ledger facts; counterparty graph (Cytoscape); cross-border
// memberships (confirm/reject); brief archive.

function who(m: Membership): string {
  return m.companies ? `${m.companies.name} (${code(m.companies)})` : m.company_id;
}

export default async function Capex({ searchParams }: { searchParams: Promise<Query> }) {
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
  return (
    <Page title="Capex Desk">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <Section title="Demand index by category" id="index">
        {index.length === 0 ? (
          <Empty>No index yet: the weekly capex job computes it from verified facts and EIA data.</Empty>
        ) : (
          <Table label="Demand index">
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead>Week</TableHead>
                <TableHead>Index (z)</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Input growth (YoY)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {index.map((r) => (
                <TableRow key={r.category}>
                  <TableCell>{r.category}</TableCell>
                  <TableCell>{r.week_end}</TableCell>
                  <TableCell>{num(r.value, 2)}</TableCell>
                  <TableCell>
                    <Badge variant={r.direction === "rising" ? "success" : r.direction === "falling" ? "destructive" : "secondary"}>{r.direction}</Badge>
                  </TableCell>
                  <TableCell>{pct(r.input_growth)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      <Section title={`Memberships waiting for a decision (${proposed.length})`} id="memberships">
        {proposed.length === 0 ? (
          <Empty>Nothing to confirm.</Empty>
        ) : (
          <ul className="flex flex-col gap-3">
            {proposed.map((m) => (
              <li key={`${m.company_id}:${m.category}`} className="rounded-md border border-gray-300 p-3 text-sm">
                <div className="font-medium">
                  <Link href={`/company/${m.company_id}`}>{who(m)}</Link> → {m.category}{" "}
                  <Badge variant="secondary">{m.source === "p06" ? "P-06 (cross-border)" : "industry map"}</Badge>
                </div>
                <p className="mt-1">{m.evidence}</p>
                {m.quote ? <blockquote className="mt-1 border-l-4 border-gray-300 pl-3">“{m.quote}”</blockquote> : null}
                <div className="mt-2 flex flex-wrap items-end gap-3">
                  <form action={decideMembership}>
                    <input type="hidden" name="company_id" value={m.company_id} />
                    <input type="hidden" name="category" value={m.category} />
                    <input type="hidden" name="decision" value="confirm" />
                    <Button type="submit" size="sm" aria-label={`Confirm ${who(m)} in ${m.category}`}>
                      Confirm
                    </Button>
                  </form>
                  <form action={decideMembership} className="flex flex-wrap items-end gap-2">
                    <input type="hidden" name="company_id" value={m.company_id} />
                    <input type="hidden" name="category" value={m.category} />
                    <input type="hidden" name="decision" value="reject" />
                    <div className="flex flex-col gap-1">
                      <Label htmlFor={`rej-${m.company_id}-${m.category}`}>Reason to reject</Label>
                      <Input id={`rej-${m.company_id}-${m.category}`} name="reason" required className="w-56" />
                    </div>
                    <Button type="submit" size="sm" variant="outline" aria-label={`Reject ${who(m)} in ${m.category}`}>
                      Reject
                    </Button>
                  </form>
                </div>
              </li>
            ))}
          </ul>
        )}
        {decided.length > 0 ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium">Decided ({decided.length})</summary>
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
                    <TableCell>{m.category}</TableCell>
                    <TableCell>{m.status}</TableCell>
                    <TableCell>{m.decision_reason ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        ) : null}
      </Section>

      <Section title="Counterparty graph" id="graph">
        {graph.edges.length === 0 ? (
          <Empty>No counterparty links yet.</Empty>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
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
                      <Link href={`/company/${e.from_company_id}`}>{e.companies?.name ?? "company"}</Link>
                    </TableCell>
                    <TableCell>{e.relation}</TableCell>
                    <TableCell>
                      {e.entities?.name ?? ""} <span className="text-gray-700">({e.entities?.kind ?? ""})</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <Section title="Ledger facts (Capex Desk companies, verified)" id="ledger">
        {ledger.length === 0 ? (
          <Empty>No verified facts yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {ledger.map((f) => (
              <li key={f.id} className="rounded-md border border-gray-300 p-3">
                <div className="font-medium">
                  {f.companies ? <Link href={`/company/${f.company_id}`}>{f.companies.name}</Link> : null} · {f.fact_type} ·{" "}
                  {f.value_num === null ? "" : f.unit === "percent" ? `${num(f.value_num)}%` : `${big(f.value_num)} ${f.unit}`} · as of {f.as_of}
                </div>
                <blockquote className="mt-1 border-l-4 border-gray-300 pl-3">“{f.quote}”</blockquote>
                {f.documents ? (
                  <a href={f.documents.url} rel="noreferrer" target="_blank">
                    {f.documents.kind} {f.documents.published_at.slice(0, 10)}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Capex brief archive" id="briefs">
        {briefs.length === 0 ? (
          <Empty>No briefs yet.</Empty>
        ) : (
          <div className="flex flex-col gap-2">
            {briefs.map((b, i) => (
              <details key={b.week_end} open={i === 0} className="rounded-md border border-gray-300 p-3">
                <summary className="cursor-pointer font-medium">Week ending {b.week_end}</summary>
                <Markdown text={b.body_md} />
              </details>
            ))}
          </div>
        )}
      </Section>
    </Page>
  );
}
