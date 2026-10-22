import { Callout } from "@/components/callout";
import { Chip, Dot, Legend, type ChipVariant } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Icon, type IconName } from "@/components/icons";
import { Markdown } from "@/components/markdown";
import { Meter } from "@/components/meter";
import { Empty, Note, Page, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CAVEATS } from "@/lib/caveats";
import { labPricesRun, labResults, weightsVersions, type LabResult } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { num, pct } from "@/lib/format";
import {
  columnGeometry,
  decileMeans,
  downloadLine,
  downloadProgress,
  headlines,
  isDecile,
  labHeadline,
  PROMOTE_WEIGHT,
  PROPOSAL_HORIZON_MONTHS,
  tally,
  verdict,
  VERDICTS,
  weightOf,
  type DownloadState,
  type Verdict,
} from "@/lib/lab";
import { SIGNAL_NAME } from "@/lib/labels";
import { signalTone } from "@/lib/palette";
import { requireUser } from "@/lib/auth";
import { cn } from "@/lib/utils";

export const metadata = { title: "Signal Lab" };

// BRIEF §6 Signal Lab (overhaul PR 4; drawn in PR 6): §7's first four honest limits at the top; each signal's verdict
// (§4.10.5) as a chip with the weight in use as a bar (weights_versions); each signal's headline result (out of
// sample at the proposal horizon) as a bar either side of the market, with every horizon and period behind Details;
// the score deciles as two small column charts (their rows behind Details); the price download's progress as a meter;
// the open proposals. Plain names on the page; the signal codes sit in each row's tooltip and in the tables.

/** A signal's plain name: S1 "Order-book acceleration", a legacy rule L3 "Legacy rule 3". */
function signalName(id: string): string {
  const legacy = /^L(\d+)$/.exec(id);
  return SIGNAL_NAME[id] ?? (legacy ? `Legacy rule ${legacy[1]}` : id);
}

function codeTitle(id: string): string {
  return SIGNAL_NAME[id] ? `${id} ${SIGNAL_NAME[id]}` : id;
}

const VERDICT_CHIP: Record<Verdict, { variant: ChipVariant; icon: IconName; word: string }> = {
  works: { variant: "good", icon: "check", word: "Works" },
  hurts: { variant: "bad", icon: "arrow-down", word: "Hurts" },
  unproven: { variant: "plain", icon: "minus", word: "Unproven" },
  "not testable yet": { variant: "plain", icon: "calendar", word: "Not testable yet" },
};

const TALLY_TEXT: Record<Verdict, string> = { works: "text-up", unproven: "text-fg", hurts: "text-down", "not testable yet": "text-subtle" };

function VerdictChip({ v }: { v: Verdict }) {
  const c = VERDICT_CHIP[v];
  return (
    <Chip variant={c.variant} size="sm" className={cn("font-semibold", v === "not testable yet" && "text-muted")}>
      <Icon name={c.icon} className="size-3.5" strokeWidth={2.4} />
      {c.word}
    </Chip>
  );
}

/** "+1.2%" or "-0.8%": an excess return with its sign. */
function signed(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "n/a";
  return `${v > 0 ? "+" : ""}${pct(v, 1)}`;
}

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
          <TableCell className="max-w-xs text-[13px] break-words text-muted">{r.notes ?? ""}</TableCell>
        </TableRow>
      ))}
    </TableBody>
  );
}

function ResultTable({ label, rows }: { label: string; rows: LabResult[] }) {
  return (
    <Table label={label}>
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
      <ResultRows rows={rows} />
    </Table>
  );
}

const DOWNLOAD_CHIP: Record<DownloadState, { variant: ChipVariant; word: string }> = {
  "not started": { variant: "plain", word: "Not started" },
  running: { variant: "accent", word: "Downloading" },
  complete: { variant: "good", word: "Complete" },
  blocked: { variant: "bad", word: "Blocked" },
};

/** The price download as a meter: tickers settled of the total, and how they settled. */
function Download({ run }: { run: Parameters<typeof downloadProgress>[0] }) {
  const p = downloadProgress(run);
  const chip = DOWNLOAD_CHIP[p.state];
  return (
    <Section
      title="Price download"
      id="download"
      quiet
      description={p.day ? `Last run ${shortDate(p.day, true)}` : undefined}
      actions={<Chip variant={chip.variant}>{chip.word}</Chip>}
    >
      {p.state === "not started" ? (
        <Empty>Not started yet. lab-prices.yml fetches Twelve Data&apos;s month-end prices first, with nothing for you to do.</Empty>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[14px] text-muted">
              <span className="num text-[30px] leading-none font-bold tracking-[-0.03em] text-fg">{p.settled.toLocaleString("en-US")}</span> of{" "}
              <span className="num">{p.total.toLocaleString("en-US")}</span> tickers
            </p>
            <span className="num text-[15px] font-semibold text-fg">{p.pct}%</span>
          </div>
          <Meter value={p.settled} max={p.total || 1} size="lg" tone={p.state === "blocked" ? "down" : p.state === "complete" ? "up" : "evidence"} label={downloadLine(run)} />
          <Legend
            items={[
              { tone: "up", label: <span className="num">{p.ok.toLocaleString("en-US")} ok</span> },
              { tone: "muted", label: <span className="num">{p.missing.toLocaleString("en-US")} no such symbol</span> },
              { tone: "down", label: <span className="num">{p.failed.toLocaleString("en-US")} failed</span> },
              ...(p.pending > 0 ? [{ tone: "evidence" as const, label: <span className="num">{p.pending.toLocaleString("en-US")} to go</span> }] : []),
            ]}
          />
          {p.state === "blocked" && p.error ? <Callout tone="bad">{p.error}</Callout> : null}
        </div>
      )}
    </Section>
  );
}

/** Ten columns either side of a zero line: a score decile's mean excess return, lowest score on the left. */
function Deciles({ name, values }: { name: string; values: (number | null)[] }) {
  const g = columnGeometry(values);
  const said = values.map((v, i) => `decile ${i + 1} ${v === null ? "no result" : signed(v)}`).join(", ");
  const high = values[values.length - 1] ?? null;
  return (
    <figure className="tile flex flex-col gap-3 p-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="text-[14px] font-semibold text-fg">{name}</span>
        {high !== null ? (
          <span className="num text-[13px] text-muted">
            top tenth <span className={cn("font-semibold", sign(high))}>{signed(high)}</span>
          </span>
        ) : null}
      </figcaption>
      <div role="img" aria-label={`${name} deciles, ${PROPOSAL_HORIZON_MONTHS}-month excess return out of sample: ${said}`} className="relative h-24">
        <div aria-hidden="true" className="absolute inset-x-0 h-px bg-line-strong" style={{ top: `${g.zero}%` }} />
        <div className="absolute inset-0 grid grid-cols-10 gap-1.5">
          {g.bars.map((b, i) => (
            <div key={i} className="relative">
              {values[i] === null ? (
                <div className="absolute inset-x-1 h-0.5 -translate-y-1/2 rounded-full bg-track" style={{ top: `${g.zero}%` }} />
              ) : b.height > 0 ? (
                <div
                  className={cn("absolute inset-x-0 rounded-[5px]", b.sign > 0 ? "bg-up" : "bg-down")}
                  style={{ top: `${b.top}%`, height: `${b.height}%` }}
                />
              ) : null}
            </div>
          ))}
        </div>
      </div>
      <div aria-hidden="true" className="flex justify-between text-[12px] text-subtle">
        <span>Lowest score</span>
        <span>Highest</span>
      </div>
    </figure>
  );
}

export default async function Lab() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [results, versions, download] = await Promise.all([labResults(), weightsVersions(), labPricesRun()]);
  const deciles = results.filter((r) => isDecile(r.signal_id));
  const signals = results.filter((r) => !isDecile(r.signal_id));
  const current = versions.find((v) => v.approved_at !== null);
  const open = versions.filter((v) => v.approved_at === null);
  const legacy = Object.keys((current?.weights.legacy as Record<string, unknown> | undefined) ?? {});
  const ids = [...new Set([...Object.keys(SIGNAL_NAME), ...legacy, ...signals.map((r) => r.signal_id)])];
  const ran = signals.length > 0;
  const rows = ids.map((id) => ({ id, v: verdict(id, signals), w: weightOf(current?.weights, id) }));
  const counts = tally(rows.map((r) => r.v));
  const heads = headlines(signals);
  const runAt = results[0]?.run_at ?? null;
  return (
    <Page
      title="Signal Lab"
      eyebrow={runAt ? `Run of ${shortDate(runAt, true)}` : "Not run yet"}
      description={labHeadline(counts, ran, downloadProgress(download).state)}
    >
      <section aria-labelledby="limits" className="rise rounded-sheet bg-warn/10 px-5 py-4 md:px-6 md:py-5">
        <h2 id="limits" className="flex items-center gap-2 text-[15px] font-semibold text-warn">
          <Icon name="alert" className="size-[18px]" />
          Honest limits
        </h2>
        <div className="mt-2 text-fg [&_.prose-md]:max-w-none [&_.prose-md]:text-[14px] [&_ol]:my-0 [&_ol]:grid [&_ol]:gap-x-8 [&_ol]:gap-y-1.5 md:[&_ol]:grid-cols-2">
          <Markdown text={CAVEATS.join("\n")} />
        </div>
      </section>

      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
          <Section
            title="Verdicts and weights"
            id="verdicts"
            description={
              current
                ? `Weights in use: version ${current.version}, approved ${shortDate(current.approved_at ?? "", true)}.`
                : "No approved weights version is recorded yet."
            }
          >
            <div className="flex flex-col gap-4">
              <ul aria-label="Verdicts, counted" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {VERDICTS.map((v) => (
                  <li key={v} className="tile flex flex-col gap-0.5 px-3.5 py-3">
                    <span className={cn("num text-[26px] leading-tight font-bold tracking-[-0.02em]", TALLY_TEXT[v])}>{counts[v]}</span>
                    <span className="text-[13px] text-muted">{VERDICT_CHIP[v].word.toLowerCase()}</span>
                  </li>
                ))}
              </ul>
              <div aria-hidden="true" className="caps hidden grid-cols-[minmax(0,1fr)_9.5rem_11rem] gap-x-4 sm:grid">
                <span>Signal</span>
                <span>Verdict</span>
                <span>Weight in use</span>
              </div>
              <ul aria-label="Verdicts and weights in use" className="-mt-2 flex flex-col">
                {rows.map(({ id, v, w }) => (
                  <li
                    key={id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 border-t border-line py-3 first:border-t-0 sm:grid-cols-[minmax(0,1fr)_9.5rem_11rem]"
                  >
                    <span className="flex min-w-0 items-center gap-2.5" title={codeTitle(id)}>
                      <Dot tone={signalTone(id)} />
                      <span className="truncate text-[15px] font-medium text-fg">{signalName(id)}</span>
                    </span>
                    <span className="justify-self-end sm:justify-self-start">
                      {!ran && v !== "not testable yet" ? <Chip size="sm" className="text-muted">No run yet</Chip> : <VerdictChip v={v} />}
                    </span>
                    <span className="col-span-2 flex items-center gap-2.5 sm:col-span-1">
                      <Meter value={w ?? 0} max={PROMOTE_WEIGHT} size="md" className="flex-1" />
                      <span className="num w-9 text-right text-[13px] font-semibold text-fg">
                        <span className="sr-only">Weight in use </span>
                        {w === null ? "–" : num(w, 1)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              <Disclosure>
                Works: beats the market out of sample at {PROPOSAL_HORIZON_MONTHS} months, clearly and in both periods, so the Lab proposes
                weight {num(PROMOTE_WEIGHT, 1)}. Hurts: clearly worse, so it proposes 0. Unproven: neither, so it proposes the neutral
                weight (not shown is not wrong). The insider, fund, text, special-situation and cycle signals read data collected only since 2026, so the
                Lab can&apos;t test them yet: they keep their weights, and verified text facts never earn weight.
              </Disclosure>
            </div>
          </Section>

          <Section
            title="Does it beat the market?"
            id="results"
            description={ran ? `Out of sample, ${PROPOSAL_HORIZON_MONTHS} months after each signal fired: its mean return above the market's.` : undefined}
          >
            {!ran ? (
              <Empty>No Lab run yet: lab-prices.yml starts the first one when the price download is complete.</Empty>
            ) : (
              <div className="flex flex-col gap-4">
                {heads.length === 0 ? (
                  <p className="text-[14px] text-muted">No signal has an out-of-sample result at {PROPOSAL_HORIZON_MONTHS} months yet.</p>
                ) : (
                  <ul aria-label={`Mean excess return, ${PROPOSAL_HORIZON_MONTHS} months, out of sample`} className="flex flex-col gap-3">
                    {heads.map((h) => (
                      <li key={h.signal} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_7.5rem]">
                        <span className="truncate text-[14px] font-medium text-fg" title={codeTitle(h.signal)}>
                          {signalName(h.signal)}
                        </span>
                        <span className="num text-right text-[13px] sm:order-last">
                          <span className={cn("font-semibold", sign(h.mean))}>{signed(h.mean)}</span>{" "}
                          <span className="text-subtle" title="Newey–West t-statistic: 2 or more is clear">
                            t {num(h.t, 1)}
                          </span>
                        </span>
                        <span aria-hidden="true" className="relative col-span-2 h-3 rounded-full bg-track sm:col-span-1">
                          <span className="absolute -inset-y-0.5 left-1/2 w-px bg-edge" />
                          <span
                            className={cn("grow-x absolute inset-y-0 rounded-full", h.mean >= 0 ? "left-1/2 bg-up" : "right-1/2 origin-right bg-down")}
                            style={{ width: `${h.share / 2}%` }}
                          />
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <Note>Right of the line: above the market&apos;s average return. Left: below it. Before dividends, taxes and costs.</Note>
                <Disclosure summary="Every horizon and period">
                  <div className="flex flex-col gap-2">
                    <ResultTable label="Lab results by signal" rows={signals} />
                    <Note>
                      Run of {signals[0]?.run_at.slice(0, 10)}. Excess returns are over the equal-weighted mean of the month&apos;s population
                      (the companies priced at both dates), before dividends, taxes and costs (BRIEF §4.10.1).
                    </Note>
                  </div>
                </Disclosure>
              </div>
            )}
          </Section>

          <Section
            title="Does a higher score pay?"
            id="deciles"
            description={deciles.length > 0 ? `Each tenth of companies by score, ${PROPOSAL_HORIZON_MONTHS} months later, out of sample.` : undefined}
          >
            {deciles.length === 0 ? (
              <Empty>No decile results yet: they come with the first Lab run.</Empty>
            ) : (
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Deciles name="Evidence" values={decileMeans(deciles, "EVIDENCE")} />
                  <Deciles name="Gap" values={decileMeans(deciles, "GAP")} />
                </div>
                <Disclosure summary="Every decile">
                  <ResultTable
                    label="Score deciles"
                    rows={[...deciles].sort((a, b) => a.signal_id.localeCompare(b.signal_id, "en", { numeric: true }))}
                  />
                </Disclosure>
              </div>
            )}
          </Section>
        </div>

        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">
          <Download run={download} />
          <Section title="Open proposals" id="proposals" quiet count={open.length}>
            <div className="flex flex-col gap-3">
              {open.length === 0 ? (
                <Empty>No open weight proposals. The Lab opens one as a pull request when a result is clear enough.</Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {open.map((v) => (
                    <li key={v.version} className="tile flex flex-col gap-1.5 p-3.5">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-[15px] font-semibold text-fg">{v.version}</span>
                        <Badge variant="warning">waiting for approval</Badge>
                      </span>
                      <p className="text-[13px] break-words text-muted">{v.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
              <Note>
                Weights change only through a pull request with the <code>human-approved</code> label.
              </Note>
            </div>
          </Section>
        </div>
      </div>
    </Page>
  );
}
