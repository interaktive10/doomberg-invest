import Link from "next/link";
import { Dot, Legend } from "@/components/chip";
import { Disclosure } from "@/components/disclosure";
import { SplitBar } from "@/components/meter";
import { Empty, Flash, Note, Page, Section } from "@/components/page";
import { SourceStatus } from "@/components/source-status";
import { SubmitButton } from "@/components/submit-button";
import { Input, Label } from "@/components/ui/input";
import { llmUse, setting, sourceHealth } from "@/lib/data";
import { shortDate } from "@/lib/dates";
import { one, type Query } from "@/lib/forms";
import { healthRows } from "@/lib/home";
import { providerLabel, sourceLabel } from "@/lib/labels";
import type { Tone } from "@/lib/palette";
import { llmLine, llmParts, sourcesLine, statusChip, tokens, type ChipTone } from "@/lib/settings";
import { sourceStatus, watched } from "@/lib/staleness";
import { saveDiscipline } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Settings" };

// BRIEF §6 Settings (overhaul PR 4; drawn in PR 6): the health of the US sources the pipeline reads as dot rows with a
// status chip (Home's Data health names them the same way, lib/home.ts healthRows), the §11.9 discipline rule
// (configurable here) and the last 7 days of LLM calls per provider as bars split into answered, rate-limited and
// failed. The config files (universes, quotas, weights) live in the repository and change through pull requests; the
// weights in use are on the Signal Lab page.

const DOT: Record<ChipTone, Tone> = { good: "up", warn: "warn", bad: "down", plain: "muted" };

/** "Sep 18, 2026, 06:00 UTC". */
function stamp(iso: string): string {
  const time = /T(\d{2}:\d{2})/.exec(iso)?.[1];
  return time ? `${shortDate(iso, true)}, ${time} UTC` : shortDate(iso, true);
}

export default async function Settings({ searchParams }: { searchParams: Promise<Query> }) {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const q = await searchParams;
  const [all, weeks, llm] = await Promise.all([
    sourceHealth(),
    setting<number | string>("position_min_thesis_weeks", 4),
    llmUse(),
  ]);
  const now = new Date();
  const sources = watched(all);
  const health = new Map(healthRows(all, now).map((h) => [h.source, h]));
  const most = Math.max(1, ...llm.map((u) => u.calls));
  const n = Number(weeks);
  return (
    <Page title="Settings" description={sourcesLine([...health.values()])}>
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
          <Section title="Sources" id="sources" description="The US sources the pipeline reads, each held to how fresh it must be.">
            {sources.length === 0 ? (
              <Empty>No source has reported yet. The first weekly run fills this in.</Empty>
            ) : (
              <ul aria-label="Sources" className="flex flex-col">
                {sources.map((s) => {
                  const chip = statusChip(sourceStatus(s, all, now));
                  const when = s.last_success ? `last success ${stamp(s.last_success)}` : "no success yet";
                  return (
                    <li key={s.source} className="flex flex-col gap-1 border-t border-line py-3.5 first:border-t-0 first:pt-1">
                      <div className="flex items-center gap-3">
                        <Dot tone={DOT[chip.tone]} className="size-2.5" />
                        <div className="flex min-w-0 flex-1 flex-col">
                          <span className="text-[15px] font-semibold text-fg">{health.get(s.source)?.name ?? sourceLabel(s.source)}</span>
                          <span className="num text-[13px] text-subtle">{[sourceLabel(s.source), when, chip.detail].filter(Boolean).join(" · ")}</span>
                        </div>
                        <SourceStatus source={s} all={all} now={now} />
                      </div>
                      {s.last_error ? (
                        <Disclosure summary="Last error" className="pl-[22px]">
                          <p className="text-[13px] break-words text-muted">{s.last_error}</p>
                        </Disclosure>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          <Section title="LLM use" id="llm" description={llmLine(llm)}>
            {llm.length === 0 ? (
              <Empty>Nothing in the last 7 days. The pipeline reads filings with free tiers only, so a quiet week costs nothing.</Empty>
            ) : (
              <ul aria-label="LLM calls by provider, last 7 days" className="flex flex-col gap-5">
                {llm.map((u) => {
                  const p = llmParts(u);
                  const name = providerLabel(u.provider);
                  return (
                    <li key={u.provider} className="flex flex-col gap-2">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[15px] font-semibold text-fg">{name}</span>
                        <span className="num text-[13px] text-muted">
                          <span className="text-[17px] font-bold text-fg">{u.calls.toLocaleString("en-US")}</span> {u.calls === 1 ? "call" : "calls"}
                        </span>
                      </div>
                      <SplitBar
                        max={most}
                        size="md"
                        label={`${name}: ${p.ok} answered, ${p.limited} rate-limited, ${p.failed} failed`}
                        parts={[
                          { value: p.ok, tone: "up", label: "answered" },
                          { value: p.limited, tone: "warn", label: "rate-limited" },
                          { value: p.failed, tone: "down", label: "failed" },
                        ]}
                      />
                      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                        <Legend
                          className="num"
                          items={[
                            { tone: "up", label: `${p.ok.toLocaleString("en-US")} answered` },
                            { tone: "warn", label: `${p.limited.toLocaleString("en-US")} rate-limited` },
                            ...(p.failed > 0 ? [{ tone: "down" as const, label: `${p.failed.toLocaleString("en-US")} failed` }] : []),
                          ]}
                        />
                        <span className="num text-[13px] text-subtle">
                          {tokens(u.tokensIn)} tokens in · {tokens(u.tokensOut)} out
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>
        </div>

        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">
          <Section title="Discipline" id="discipline" quiet>
            <div className="flex flex-col gap-4">
              <p className="text-[15px] text-fg">
                A thesis waits{" "}
                <span className="num text-[22px] font-bold tracking-[-0.02em]">{Number.isFinite(n) ? n : String(weeks)}</span>{" "}
                {n === 1 ? "week" : "weeks"} before a start position. Earlier needs a written reason.
              </p>
              <form action={saveDiscipline} className="flex flex-col gap-1.5">
                <Label htmlFor="weeks">Weeks a thesis must be old before a start-position entry</Label>
                <div className="flex items-center gap-2">
                  <Input id="weeks" name="weeks" type="number" min="0" max="104" step="1" defaultValue={String(weeks)} className="w-28" required />
                  <SubmitButton>Save</SubmitButton>
                </div>
              </form>
            </div>
          </Section>
          <Note className="px-1">
            Universes, quotas and weights live in the repository&apos;s config files and change through pull requests. The weights in use are
            in the <Link href="/lab">Signal Lab</Link>.
          </Note>
        </div>
      </div>
    </Page>
  );
}
