import type { ReactNode } from "react";
import { Empty, Note, Section } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { WhyData } from "@/lib/data";
import { num, pct } from "@/lib/format";
import { verdict, type Verdict } from "@/lib/lab";
import { CONTEXT_NAME, dcfRows, FAMILY_LABEL, label, RED_FLAG_NAME, SIGNAL_NAME } from "@/lib/labels";
import { breakdown, capWords, EVIDENCE_DIVISOR, firingSince, gapParts, inputRows, SOFT_FLAG_PENALTY, type InputRow } from "@/lib/why";
import { cn } from "@/lib/utils";

/** Signal family ids as badges with their names (the Company page's score line). */
export function FamilyBadges({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((f) => (
        <Badge key={f} variant="secondary">
          {label(FAMILY_LABEL, f)}
        </Badge>
      ))}
    </span>
  );
}

const VERDICT_BADGE: Record<Verdict, "success" | "destructive" | "outline" | "secondary"> = {
  works: "success",
  hurts: "destructive",
  unproven: "secondary",
  "not testable yet": "outline",
};

/** Stored inputs as a two-column list: the name (or the raw key) and the value in mono. */
function Inputs({ rows }: { rows: InputRow[] }) {
  if (rows.length === 0) return <p className="text-xs text-muted">No inputs stored.</p>;
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-xs sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
      {rows.map((r) => (
        <div key={r.key} className="contents">
          <dt className="text-muted">{r.label}</dt>
          <dd className="num text-right break-words text-fg sm:text-left">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Sub({ children }: { children: ReactNode }) {
  return <h3 className="caps mb-2">{children}</h3>;
}

/** "Why this score" at the top of the Company page (overhaul PR 5; BRIEF §4.8): Evidence by family with the one-family
 * cap in words, each fired signal with its strength, inputs, firing since and Lab verdict, the red flags with their
 * inputs, and the Gap split into C1-C3 with the reverse DCF folded into C2. */
export function WhyThisScore({
  score,
  why,
}: {
  score: { week_end: string; evidence: number | string; gap: number | string | null; weights_version: string } | null;
  why: WhyData | null;
}) {
  if (score === null || why === null) {
    return (
      <Section title="Why this score" id="why">
        <Empty>Not scored yet. The weekly run scores the universe and every research entry each Saturday.</Empty>
      </Section>
    );
  }
  const soft = why.flags.filter((f) => !f.hard).length;
  const b = breakdown(why.signals, why.weights, soft);
  const fired = why.signals.filter((s) => s.fired);
  const gap = gapParts(why.context);
  return (
    <Section
      title="Why this score"
      id="why"
      description={
        <>
          Week ending <span className="num">{score.week_end}</span> · weights <span className="num">{score.weights_version}</span>. Evidence
          never uses price; Gap does.
        </>
      }
    >
      <div className="flex flex-col gap-6">
        <div>
          <Sub>Evidence by family</Sub>
          {b.families.length === 0 ? (
            <p className="text-[13px] text-muted">No signal fired this week.</p>
          ) : (
            <Table label="Evidence by family">
              <TableHeader>
                <TableRow>
                  <TableHead>Family</TableHead>
                  <TableHead>Signals that count</TableHead>
                  <TableHead num>Contribution</TableHead>
                  <TableHead num>Points</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {b.families.map((f) => (
                  <TableRow key={f.family}>
                    <TableCell>{label(FAMILY_LABEL, f.family)}</TableCell>
                    <TableCell className="num">
                      {f.counted.join(", ")}
                      {f.beyond.length > 0 ? <span className="text-muted"> (not counted, top 2 only: {f.beyond.join(", ")})</span> : null}
                    </TableCell>
                    <TableCell num>{f.contribution.toFixed(2)}</TableCell>
                    <TableCell num>{f.points.toFixed(1)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <p className="mt-2 text-[13px] text-fg">{capWords(b)}</p>
          <Note className="mt-1">
            Stored Evidence <span className="num text-fg">{num(score.evidence)}</span>; the rules above give{" "}
            <span className="num text-fg">{b.evidence.toFixed(1)}</span>. A family&apos;s points are 100 × its weight × its contribution /{" "}
            {EVIDENCE_DIVISOR}; a contribution is the sum of its top two weight × strength, at most 1.
          </Note>
        </div>

        <div>
          <Sub>Signals that fired</Sub>
          {fired.length === 0 ? (
            <p className="text-[13px] text-muted">None this week.</p>
          ) : (
            <ul className="flex flex-col">
              {fired.map((s) => {
                const since = firingSince(score.week_end, why.scoredWeeks, why.fired.get(s.signal_id) ?? new Set());
                const v = verdict(s.signal_id, why.lab);
                return (
                  <li key={s.signal_id} className="flex flex-col gap-2 border-t border-line py-3 first:border-t-0 first:pt-0">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                      <span className="font-semibold text-fg">
                        <span className="num">{s.signal_id}</span> {SIGNAL_NAME[s.signal_id] ?? ""}
                      </span>
                      <span className="text-muted">
                        strength <span className="num text-fg">{num(s.strength, 2)}</span>
                      </span>
                      <span className="text-muted">
                        firing since <span className="num text-fg">{since ?? score.week_end}</span>
                      </span>
                      <span className="text-muted">
                        Lab <Badge variant={VERDICT_BADGE[v]}>{v}</Badge>
                      </span>
                    </div>
                    <Inputs rows={inputRows(s.inputs)} />
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div>
          <Sub>Red flags</Sub>
          {why.flags.length === 0 ? (
            <p className="text-[13px] text-muted">None fired this week.</p>
          ) : (
            <ul className="flex flex-col">
              {why.flags.map((f) => (
                <li key={f.flag_id} className="flex flex-col gap-2 border-t border-line py-3 first:border-t-0 first:pt-0">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                    <span className={cn("font-semibold", f.hard ? "text-down" : "text-warn")}>
                      <span className="num">{f.flag_id}</span> {RED_FLAG_NAME[f.flag_id] ?? ""}
                    </span>
                    <span className="text-muted">{f.hard ? "hard: excludes the company" : `soft: subtracts ${SOFT_FLAG_PENALTY}`}</span>
                  </div>
                  <Inputs rows={inputRows(f.inputs, ["status"])} />
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <Sub>Gap (uses price)</Sub>
          <ul className="flex flex-col">
            {gap.parts.map((p) => (
              <li key={p.id} className="flex flex-col gap-2 border-t border-line py-3 first:border-t-0 first:pt-0">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                  <span className="font-semibold text-fg">
                    <span className="num">{p.id}</span> {CONTEXT_NAME[p.id] ?? ""}
                  </span>
                  {p.score === null ? (
                    <span className="text-warn">{p.missing}</span>
                  ) : (
                    <span className="text-muted">
                      score <span className="num text-fg">{p.score.toFixed(0)}</span>
                    </span>
                  )}
                  {p.id === "C2" && p.row && p.row.value !== null ? (
                    <span className="text-muted">
                      evidence growth minus implied growth <span className="num text-fg">{pct(p.row.value)}</span>
                    </span>
                  ) : null}
                </div>
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
          <p className="mt-2 text-[13px] text-fg">
            {gap.mean === null
              ? `Gap needs at least 2 of C1-C3; with ${gap.parts.filter((p) => p.score !== null).length}, it has none (bucket "No bucket").`
              : `Gap = the mean of ${gap.parts.filter((p) => p.score !== null).map((p) => p.id).join(", ")} = ${gap.mean.toFixed(1)}`}
            {gap.mean !== null ? (
              <span className="text-muted">
                {" "}
                (stored <span className="num text-fg">{num(score.gap)}</span>).
              </span>
            ) : null}
          </p>
        </div>
      </div>
    </Section>
  );
}
