import type { ReactNode } from "react";
import { Callout } from "@/components/callout";
import { Chip, Dot, Legend, type ChipVariant } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { Meter, SplitBar } from "@/components/meter";
import { Empty, Section } from "@/components/page";
import type { WhyData } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { capShort, familyWord, GAP_SHORT, gapLine, signalLine, signalShort } from "@/lib/explain";
import { num, pct } from "@/lib/format";
import { verdict, type Verdict } from "@/lib/lab";
import { CONTEXT_NAME, dcfRows, FAMILY_LABEL, label, RED_FLAG_NAME, SIGNAL_NAME } from "@/lib/labels";
import { familyTone, signalTone } from "@/lib/palette";
import { breakdown, capWords, EVIDENCE_DIVISOR, firingSince, gapParts, inputRows, SOFT_FLAG_PENALTY, type InputRow } from "@/lib/why";
import { cn } from "@/lib/utils";

const VERDICT_CHIP: Record<Verdict, ChipVariant> = {
  works: "good",
  hurts: "bad",
  unproven: "plain",
  "not testable yet": "plain",
};

/** Stored inputs as a two-column list (inside a Details disclosure): the name (or the raw key) and the value. */
function Inputs({ rows }: { rows: InputRow[] }) {
  if (rows.length === 0) return <p className="text-[13px] text-subtle">No inputs stored.</p>;
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-[13px] sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
      {rows.map((r) => (
        <div key={r.key} className="contents">
          <dt className="text-muted">{r.label}</dt>
          <dd className="num text-right break-words text-fg sm:text-left">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A block's small title ("EVIDENCE 72") with a few words on the right. */
function Head({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <h3 className="eyebrow">{children}</h3>
      {note ? <span className="text-[13px] text-subtle">{note}</span> : null}
    </div>
  );
}

function n(v: number | string | null): number | null {
  const x = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : Number.NaN;
  return Number.isFinite(x) ? x : null;
}

/** "Why this score" on the Company page (overhaul PR 5; BRIEF §4.8), drawn (overhaul PR 6): Evidence as one bar split
 * by kind of evidence, one row per fired signal in plain words with its strength bar and Lab verdict, the Gap's three
 * parts as tiles (a part without a score says why), and the red flags as one green line or a row each. The workings
 * (the cap rule, the codes, each signal's inputs and firing-since week, the reverse DCF) sit behind Why and Details. */
export function WhyThisScore({
  score,
  why,
  className,
}: {
  score: { week_end: string; evidence: number | string; gap: number | string | null; bucket: string; weights_version: string } | null;
  why: WhyData | null;
  className?: string;
}) {
  if (score === null || why === null) {
    return (
      <Section title="Why this score" id="why" className={className}>
        <Empty>Not scored yet. The weekly run scores the universe and every research entry each Saturday.</Empty>
      </Section>
    );
  }
  const soft = why.flags.filter((f) => !f.hard).length;
  const b = breakdown(why.signals, why.weights, soft);
  const fired = why.signals.filter((s) => s.fired);
  const gap = gapParts(why.context);
  const scored = gap.parts.filter((p) => p.score !== null);
  const kinds = b.families.map((f) => ({ value: f.points, tone: familyTone(f.family), label: familyWord(f.family, f.counted) }));
  return (
    <Section
      title="Why this score"
      id="why"
      className={className}
      actions={<span className="num text-[13px] text-subtle">Week ending {shortDate(score.week_end, true)}</span>}
    >
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2.5">
          <Head note={capShort(b)}>Evidence {num(score.evidence, 0)}</Head>
          <SplitBar
            parts={kinds}
            label={kinds.length === 0 ? "No evidence this week" : `${kinds.map((k) => `${k.label} ${Math.round(k.value)}`).join(", ")} of 100`}
          />
          {kinds.length > 0 ? <Legend items={kinds.map((k) => ({ tone: k.tone, label: `${k.label} ${Math.round(k.value)}` }))} /> : null}
          <Disclosure summary="Why">
            <div className="flex flex-col gap-2">
              <p className="text-fg">{capWords(b)}</p>
              {b.families.length > 0 ? (
                <ul className="flex flex-col gap-1">
                  {b.families.map((f) => (
                    <li key={f.family}>
                      <span className="font-semibold text-fg">{familyWord(f.family, f.counted)}</span> ({label(FAMILY_LABEL, f.family)}):{" "}
                      <span className="num">{f.counted.join(", ")}</span> {f.counted.length === 1 ? "counts" : "count"}
                      {f.beyond.length > 0 ? (
                        <>
                          ; <span className="num">{f.beyond.join(", ")}</span> {f.beyond.length === 1 ? "adds" : "add"} nothing past the top two
                        </>
                      ) : null}{" "}
                      · <span className="num">{f.points.toFixed(1)}</span> points
                    </li>
                  ))}
                </ul>
              ) : null}
              <p>
                Stored Evidence <span className="num text-fg">{num(score.evidence)}</span>; the rules give{" "}
                <span className="num text-fg">{b.evidence.toFixed(1)}</span>. A family&apos;s points are 100 × its weight × its contribution /{" "}
                {EVIDENCE_DIVISOR}; a contribution is the sum of its top two weight × strength, at most 1. Weights{" "}
                <span className="num text-fg">{score.weights_version}</span>.
              </p>
              <p>Evidence never uses the price; Gap does.</p>
            </div>
          </Disclosure>
        </div>

        {fired.length === 0 ? (
          <p className="text-[14px] text-muted">No signal fired this week.</p>
        ) : (
          <ul aria-label="Signals that fired" className="flex flex-col gap-2.5">
            {fired.map((s) => {
              const since = firingSince(score.week_end, why.weeks, why.fired.get(s.signal_id) ?? new Set());
              const v = verdict(s.signal_id, why.lab);
              const tone = signalTone(s.signal_id);
              return (
                <li key={s.signal_id} className="tile rise flex gap-3.5 p-4">
                  <Dot tone={tone} className="mt-1.5 size-2.5" />
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[15px] font-semibold text-fg">{signalShort(s.signal_id)}</span>
                      <Chip variant={VERDICT_CHIP[v]} size="sm" title="The Signal Lab's verdict on this signal's past returns">
                        Lab: {v}
                      </Chip>
                    </div>
                    <p className="text-[14px] text-muted">{signalLine(s.signal_id, s.inputs)}</p>
                    <div className="flex items-center gap-2.5">
                      <Meter value={n(s.strength) ?? 0} max={1} tone={tone} className="flex-1" />
                      <span className="num text-[13px] font-semibold text-fg">
                        <span className="sr-only">Strength </span>
                        {num(s.strength, 2)}
                      </span>
                    </div>
                    <Disclosure summary="Details">
                      <p className="mb-2 text-fg">
                        <span className="num">{s.signal_id}</span> {SIGNAL_NAME[s.signal_id] ?? ""} · firing since{" "}
                        <span className="num">{since ?? score.week_end}</span>
                      </p>
                      <Inputs rows={inputRows(s.inputs)} />
                    </Disclosure>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex flex-col gap-2.5">
          <Head note={gap.mean === null ? "needs 2 of its 3 parts" : "average of the parts scored"}>
            {score.gap === null ? "Gap" : `Gap ${num(score.gap, 0)}`}
          </Head>
          <ul aria-label="Parts of the Gap" className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            {gap.parts.map((p) => (
              <li key={p.id} className="tile flex flex-col gap-1.5 p-3.5" title={`${p.id}: ${CONTEXT_NAME[p.id] ?? ""}`}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[13px] font-semibold text-fg">{GAP_SHORT[p.id]}</span>
                  {p.score === null ? (
                    <span className="num text-[20px] font-bold text-subtle">
                      <span aria-hidden="true">–</span>
                      <span className="sr-only">not scored</span>
                    </span>
                  ) : (
                    <span className="num text-[20px] font-bold text-up">{p.score.toFixed(0)}</span>
                  )}
                </div>
                <p className={cn("text-[13px]", p.score === null ? "text-warn" : "text-muted")}>{gapLine(p)}</p>
              </li>
            ))}
          </ul>
          <Disclosure summary="Details">
            <ul className="flex flex-col gap-3">
              {gap.parts.map((p) => (
                <li key={p.id}>
                  <p className="mb-1 text-fg">
                    <span className="num">{p.id}</span> {CONTEXT_NAME[p.id] ?? ""} ·{" "}
                    {p.score === null ? p.missing : <span className="num">score {p.score.toFixed(0)}</span>}
                    {p.id === "C2" && p.row && p.row.value !== null ? (
                      <>
                        {" "}
                        · evidence growth minus implied growth <span className="num">{pct(p.row.value)}</span>
                      </>
                    ) : null}
                  </p>
                  {p.row ? (
                    <Inputs
                      rows={
                        p.id === "C2"
                          ? dcfRows(Object.fromEntries(Object.entries(p.row.inputs ?? {}).filter(([k]) => k !== "score" && k !== "missing")))
                          : inputRows(p.row.inputs, ["score", "missing"])
                      }
                    />
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="mt-3">
              {gap.mean === null
                ? `Gap needs at least 2 of C1-C3; with ${scored.length}, it has none.`
                : `Gap = the mean of ${scored.map((p) => p.id).join(", ")} = ${gap.mean.toFixed(1)}`}
              {gap.mean !== null ? (
                <>
                  {" "}
                  (stored <span className="num text-fg">{num(score.gap)}</span>). Gap uses the price; Evidence never does.
                </>
              ) : null}
            </p>
          </Disclosure>
        </div>

        {why.flags.length === 0 ? (
          <Callout tone="good">No red flags: no auditor change, late filing, dilution or cash-flow warning.</Callout>
        ) : (
          <ul aria-label="Red flags" className="flex flex-col gap-2">
            {why.flags.map((f) => (
              <li key={f.flag_id}>
                <Callout tone={f.hard ? "bad" : "warn"}>
                  <p>
                    <span className="font-semibold text-fg">{RED_FLAG_NAME[f.flag_id] ?? f.flag_id}</span>{" "}
                    <span className={f.hard ? "text-down" : "text-warn"}>
                      · {f.hard ? "hard: excludes the company" : `soft: takes ${SOFT_FLAG_PENALTY} off Evidence`}
                    </span>
                  </p>
                  <Disclosure summary="Details">
                    <p className="mb-2">
                      Red flag <span className="num">{f.flag_id}</span>
                    </p>
                    <Inputs rows={inputRows(f.inputs, ["status"])} />
                  </Disclosure>
                </Callout>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}
