import { Markdown } from "@/components/markdown";
import { Empty, Note, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CAVEATS } from "@/lib/caveats";
import { labPricesRun, labResults, weightsVersions, type LabResult } from "@/lib/data";
import { num, pct } from "@/lib/format";
import { downloadLine, PROPOSAL_HORIZON_MONTHS, verdict, weightOf, type Verdict } from "@/lib/lab";
import { SIGNAL_NAME } from "@/lib/labels";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Signal Lab" };

// BRIEF §6 Signal Lab (overhaul PR 4): the price download's progress, each signal's verdict (§4.10.5) with the weight
// in use (weights_versions), results by signal, horizon and period, score deciles and open proposals. §7: the first
// four honest limits at the top of the screen.
const DECILE = /^(EVIDENCE|GAP)_D(\d+)$/;

const VERDICT_BADGE: Record<Verdict, "success" | "destructive" | "secondary" | "outline"> = {
  works: "success",
  hurts: "destructive",
  unproven: "secondary",
  "not testable yet": "outline",
};

/** An excess return's colour by its sign: up above zero, down below. */
function sign(v: number | null): string | undefined {
  const n = Number(v);
  return v === null || !Number.isFinite(n) || n === 0 ? undefined : n > 0 ? "text-up" : "text-down";
}

function ResultRows({ rows }: { rows: LabResult[] }) {
  return (
    <TableBody>
      {rows.map((r) => (
        <TableRow key={`${r.signal_id}:${r.market}:${r.horizon_m}:${r.period}`}>
          <TableCell className="font-medium whitespace-nowrap" title={SIGNAL_NAME[r.signal_id]}>
            {r.signal_id}
          </TableCell>
          <TableCell>{r.market.toUpperCase()}</TableCell>
          <TableCell num>{r.horizon_m}m</TableCell>
          <TableCell>
            <Badge variant={r.period === "in_sample" ? "secondary" : "default"}>{r.period === "in_sample" ? "in sample" : "out of sample"}</Badge>
          </TableCell>
          <TableCell num>{r.n.toLocaleString("en-US")}</TableCell>
          <TableCell num className={sign(r.excess_mean)}>
            {pct(r.excess_mean, 2)}
          </TableCell>
          <TableCell num className={sign(r.excess_median)}>
            {pct(r.excess_median, 2)}
          </TableCell>
          <TableCell num>{pct(r.hit_rate, 0)}</TableCell>
          <TableCell num>{pct(r.p10, 2)}</TableCell>
          <TableCell num>{num(r.t_nw, 2)}</TableCell>
          <TableCell className="max-w-xs text-xs break-words text-muted">{r.notes ?? ""}</TableCell>
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
        <TableHead num>Horizon</TableHead>
        <TableHead>Period</TableHead>
        <TableHead num>n</TableHead>
        <TableHead num>Excess mean</TableHead>
        <TableHead num>Excess median</TableHead>
        <TableHead num>Hit rate</TableHead>
        <TableHead num>p10</TableHead>
        <TableHead num>
          <abbr title="Newey–West t-statistic">t (NW)</abbr>
        </TableHead>
        <TableHead>Notes</TableHead>
      </TableRow>
    </TableHeader>
  );
}

export default async function Lab() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [results, versions, download] = await Promise.all([labResults(), weightsVersions(), labPricesRun()]);
  const deciles = results.filter((r) => DECILE.test(r.signal_id));
  const signals = results.filter((r) => !DECILE.test(r.signal_id));
  const current = versions.find((v) => v.approved_at !== null);
  const open = versions.filter((v) => v.approved_at === null);
  const legacy = Object.keys((current?.weights.legacy as Record<string, unknown> | undefined) ?? {});
  const ids = [...new Set([...Object.keys(SIGNAL_NAME), ...legacy, ...signals.map((r) => r.signal_id)])];
  return (
    <Page title="Signal Lab" description="Does each signal beat its market out of sample? The Lab measures it; weights change only through a reviewed pull request.">
      <p className="num rounded-md border border-line bg-panel px-4 py-2.5 text-[13px] text-fg">{downloadLine(download)}</p>
      <section aria-labelledby="limits" className="rounded-md border border-warn/40 border-l-2 border-l-warn bg-warn/10 p-4">
        <h2 id="limits" className="text-sm font-semibold text-warn">
          Honest limits
        </h2>
        <div className="mt-1 text-fg [&_.prose-md]:max-w-none">
          <Markdown text={CAVEATS.join("\n")} />
        </div>
      </section>
      <Section
        title="Verdicts and weights in use"
        id="verdicts"
        description={
          <>
            Each signal&apos;s verdict at {PROPOSAL_HORIZON_MONTHS} months (§4.10.5): works, hurts, or unproven (not shown, not wrong).
            {current
              ? ` Weights in use: version ${current.version}, approved ${current.approved_at?.slice(0, 10) ?? ""}.`
              : " No approved weights version is recorded yet."}
          </>
        }
      >
        <Table label="Verdicts and weights in use">
          <TableHeader>
            <TableRow>
              <TableHead>Signal</TableHead>
              <TableHead>Verdict</TableHead>
              <TableHead num>Weight in use</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ids.map((id) => {
              const v = verdict(id, signals);
              const w = weightOf(current?.weights, id);
              return (
                <TableRow key={id}>
                  <TableCell className="whitespace-nowrap">
                    <span className="font-medium">{id}</span> <span className="text-muted">{SIGNAL_NAME[id] ?? (id.startsWith("L") ? "legacy rule" : "")}</span>
                  </TableCell>
                  <TableCell>
                    {signals.length === 0 && v !== "not testable yet" ? (
                      <span className="text-muted">no Lab run yet</span>
                    ) : (
                      <Badge variant={VERDICT_BADGE[v]}>{v}</Badge>
                    )}
                  </TableCell>
                  <TableCell num>{w === null ? "–" : num(w, 1)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <Note className="mt-3">S7–S12 read data collected only since 2026, so the Lab can&apos;t test them yet; they keep their weights, and S9 never earns weight.</Note>
      </Section>
      <Section
        title="Results by signal, horizon and period"
        id="results"
        description={
          signals.length > 0
            ? `Run of ${signals[0]?.run_at.slice(0, 10)}. Excess returns are over the equal-weighted mean of the month's population (the companies priced at both dates), before dividends, taxes and costs (BRIEF §4.10.1).`
            : undefined
        }
      >
        {signals.length === 0 ? (
          <Empty>No Lab run yet: lab-prices.yml dispatches the first one when the price download is complete.</Empty>
        ) : (
          <Table label="Lab results by signal">
            <Head />
            <ResultRows rows={signals} />
          </Table>
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
          <ul className="flex flex-col gap-2 text-[13px]">
            {open.map((v) => (
              <li key={v.version} className="rounded-sm border border-line bg-canvas p-3">
                <span className="font-medium">{v.version}</span> <Badge variant="warning">not approved</Badge>
                <p className="mt-1 break-words">{v.reason}</p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[13px] text-muted">
          Weights change only through a pull request with the <code>human-approved</code> label (config/weights.yaml).
        </p>
      </Section>
    </Page>
  );
}
