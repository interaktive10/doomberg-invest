import { Markdown } from "@/components/markdown";
import { Empty, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CAVEATS } from "@/lib/caveats";
import { labResults, weightsVersions, type LabResult } from "@/lib/data";
import { num, pct } from "@/lib/format";
import { requireUser } from "@/lib/auth";

// BRIEF §6 Signal Lab: results by signal, horizon and period; score deciles; weights versions; open proposals. §7:
// the first four honest limits at the top of the screen.
const DECILE = /^(EVIDENCE|GAP)_D(\d+)$/;

function ResultRows({ rows }: { rows: LabResult[] }) {
  return (
    <TableBody>
      {rows.map((r) => (
        <TableRow key={`${r.signal_id}:${r.market}:${r.horizon_m}:${r.period}`}>
          <TableCell>{r.signal_id}</TableCell>
          <TableCell>{r.market.toUpperCase()}</TableCell>
          <TableCell>{r.horizon_m}m</TableCell>
          <TableCell>{r.period === "in_sample" ? "in sample" : "out of sample"}</TableCell>
          <TableCell>{r.n}</TableCell>
          <TableCell>{pct(r.excess_mean, 2)}</TableCell>
          <TableCell>{pct(r.excess_median, 2)}</TableCell>
          <TableCell>{pct(r.hit_rate, 0)}</TableCell>
          <TableCell>{pct(r.p10, 2)}</TableCell>
          <TableCell>{num(r.t_nw, 2)}</TableCell>
          <TableCell className="max-w-xs break-words text-xs">{r.notes ?? ""}</TableCell>
        </TableRow>
      ))}
    </TableBody>
  );
}

function Head() {
  return (
    <TableHeader>
      <TableRow>
        <TableHead>Signal</TableHead>
        <TableHead>Market</TableHead>
        <TableHead>Horizon</TableHead>
        <TableHead>Period</TableHead>
        <TableHead>n</TableHead>
        <TableHead>Excess mean</TableHead>
        <TableHead>Excess median</TableHead>
        <TableHead>Hit rate</TableHead>
        <TableHead>p10</TableHead>
        <TableHead>t (NW)</TableHead>
        <TableHead>Notes</TableHead>
      </TableRow>
    </TableHeader>
  );
}

export default async function Lab() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [results, versions] = await Promise.all([labResults(), weightsVersions()]);
  const deciles = results.filter((r) => DECILE.test(r.signal_id));
  const signals = results.filter((r) => !DECILE.test(r.signal_id));
  const approved = versions.filter((v) => v.approved_at !== null);
  const open = versions.filter((v) => v.approved_at === null);
  return (
    <Page title="Signal Lab">
      <section aria-labelledby="limits" className="rounded-md border border-amber-700 bg-amber-50 p-3">
        <h2 id="limits" className="font-semibold">
          Honest limits
        </h2>
        <Markdown text={CAVEATS.join("\n")} />
      </section>
      <Section title="Results by signal, horizon and period" id="results">
        {signals.length === 0 ? (
          <Empty>No Lab run yet (lab.yml, manual; it needs the Stooq bulk file).</Empty>
        ) : (
          <>
            <p className="mb-2 text-sm text-gray-700">Run of {signals[0]?.run_at.slice(0, 10)}. Excess returns are over the equal-weighted mean of the month&apos;s population (the companies priced at both dates), before dividends, taxes and costs (BRIEF §4.10.1).</p>
            <Table label="Lab results by signal">
              <Head />
              <ResultRows rows={signals} />
            </Table>
          </>
        )}
      </Section>
      <Section title="Score deciles (Evidence and Gap)" id="deciles">
        {deciles.length === 0 ? (
          <Empty>No decile results yet.</Empty>
        ) : (
          <Table label="Score deciles">
            <Head />
            <ResultRows rows={[...deciles].sort((a, b) => a.signal_id.localeCompare(b.signal_id, "en", { numeric: true }))} />
          </Table>
        )}
      </Section>
      <Section title="Open proposals (not approved)" id="proposals">
        {open.length === 0 ? (
          <Empty>No open weight proposals.</Empty>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {open.map((v) => (
              <li key={v.version} className="rounded-md border border-gray-300 p-3">
                <span className="font-medium">{v.version}</span> <Badge variant="warning">not approved</Badge>
                <p className="mt-1 break-words">{v.reason}</p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-sm text-gray-700">
          Weights change only through a pull request with the <code>human-approved</code> label (config/weights.yaml).
        </p>
      </Section>
      <Section title="Weights versions" id="weights">
        {approved.length === 0 ? (
          <Empty>No approved weights version recorded yet.</Empty>
        ) : (
          <Table label="Weights versions">
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>Approved</TableHead>
                <TableHead>By</TableHead>
                <TableHead>Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {approved.map((v) => (
                <TableRow key={v.version}>
                  <TableCell>{v.version}</TableCell>
                  <TableCell>{v.approved_at?.slice(0, 10)}</TableCell>
                  <TableCell>{v.approved_by ?? ""}</TableCell>
                  <TableCell className="max-w-md break-words">{v.reason}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
    </Page>
  );
}
