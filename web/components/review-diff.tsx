import type { ReactNode } from "react";
import { Chip, type ChipVariant } from "@/components/chip";
import { Badge } from "@/components/ui/badge";
import { shortDate } from "@/lib/dates";
import { GAP_SHORT, killRule, KILL_WORD, pc, signalShort } from "@/lib/explain";
import { big, num } from "@/lib/format";
import { RED_FLAG_NAME } from "@/lib/labels";
import { changeLines, contextValue, killValue, type KillSnapshot, type PackDiff, type StateDiff } from "@/lib/reviews";

// A review's pack diff (BRIEF §4.9 "the pack diff since the last review"; M7 review R1-F4), as clean rows (overhaul
// PR 6): the quarter's key figures against the quarter before with the change, the kill criteria as they stood (in
// their metric's unit, as the checklist beside them), and what changed since the last review (or the card): only the
// signals and red flags that did, by name (the codes in their titles), the context (Evidence and Gap as whole scores),
// new verified facts as quotes, ownership filings and insider events (PR 6 final review V4-2, V4-9).

const FIGURE_LABEL: Record<string, string> = {
  revenue: "Revenue",
  op_income: "Operating income",
  net_income: "Net income",
  cfo: "Cash from operations",
  rpo: "RPO",
  diluted_shares: "Diluted shares",
};

const CONTEXT_LABEL: Record<string, string> = { ...GAP_SHORT, evidence: "Evidence", gap: "Gap" };

/** A date as the screens say it ("Jun 30, 2026"), the ISO date kept for machines; a value that isn't a date as it is. */
function Day({ iso }: { iso: string }) {
  return (
    <time dateTime={iso.slice(0, 10)} className="num">
      {shortDate(iso, true)}
    </time>
  );
}

function arrow(before: number | null, now: number | null, fmt: (v: number | null) => string): string {
  return `${fmt(before)} → ${fmt(now)}`;
}

/** The change as a chip: up is good and down is bad, except for the share count, where it is the other way round. None
 * from a zero or negative base (a loss turning into a profit has no percentage). */
function Change({ name, before, now }: { name: string; before: number | null; now: number | null }) {
  if (before === null || now === null || !(before > 0)) return null;
  const ch = now / before - 1;
  if (!Number.isFinite(ch)) return null;
  const good = name === "diluted_shares" ? ch <= 0 : ch >= 0;
  const variant: ChipVariant = Math.abs(ch) < 0.005 ? "plain" : good ? "good" : "bad";
  return (
    <Chip variant={variant} size="sm">
      <span className="num">
        {ch >= 0 ? "+" : "−"}
        {pc(Math.abs(ch))}
      </span>
    </Chip>
  );
}

/** A labelled list of rows: a region a test (and a screen reader) can name. */
function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="region" aria-label={label} className="min-w-0">
      <ul className="flex flex-col">{children}</ul>
    </div>
  );
}

function Row({ name, title, value, end }: { name: ReactNode; title?: string; value: ReactNode; end?: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0 first:pt-0">
      <span className="min-w-0 text-[14px] text-fg" title={title}>
        {name}
      </span>
      <span className="flex items-center gap-2">
        <span className="num text-[14px] whitespace-nowrap text-fg">{value}</span>
        {end}
      </span>
    </li>
  );
}

function KillRows({ label, kills, state }: { label: string; kills: readonly KillSnapshot[]; state: StateDiff | null }) {
  const before = new Map((state?.kill ?? []).map((k) => [k.metric, k.before]));
  return (
    <Rows label={label}>
      {kills.map((k) => (
        <Row
          key={k.metric}
          name={killRule(k)}
          title={k.metric}
          value={arrow(before.get(k.metric) ?? null, k.last_value, (v) => killValue(k.metric, v))}
          end={<Badge variant={k.status === "triggered" ? "destructive" : k.status === "ok" ? "success" : "secondary"}>{KILL_WORD[k.status] ?? k.status}</Badge>}
        />
      ))}
    </Rows>
  );
}

/** Ids as their names, each with its code as the title: "Order book, Insider buying". */
function Names({ ids, name }: { ids: readonly string[]; name: (id: string) => string }) {
  return (
    <>
      {ids.map((id, i) => (
        <span key={id} title={id}>
          {i > 0 ? ", " : ""}
          {name(id)}
        </span>
      ))}
    </>
  );
}

const flagName = (f: string) => RED_FLAG_NAME[f] ?? f;

function Changes({ id, state }: { id: string; state: StateDiff }) {
  const lines = changeLines(state);
  return (
    <div className="flex flex-col gap-2.5 text-[14px] text-fg">
      <h3 className="eyebrow">What changed {state.since ? <>since {shortDate(state.since, true)}</> : "since the card"}</h3>
      {lines.length === 0 ? (
        <p className="text-muted">No signal or red flag changes.</p>
      ) : (
        lines.map((l) => (
          <p key={l.lead}>
            <span className="font-semibold">{l.lead}:</span> <Names ids={l.ids} name={l.kind === "signal" ? signalShort : flagName} />.
          </p>
        ))
      )}
      {state.context.length > 0 ? (
        <Rows label={`Context for review ${id}`}>
          {state.context.map((c) => (
            <Row key={c.id} name={CONTEXT_LABEL[c.id] ?? c.id} title={c.id} value={arrow(c.before, c.now, (v) => contextValue(c.id, v))} />
          ))}
        </Rows>
      ) : null}
      {state.facts.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {state.facts.map((f) => (
            <li key={f.id} className="rounded-tile bg-panel p-3">
              <p className="text-[13px] text-muted">
                New fact (as of <Day iso={f.as_of} />
                {f.published_at ? (
                  <>
                    , published <Day iso={f.published_at} />
                  </>
                ) : null}
                ): {f.subject}{" "}
                {f.value === null ? "" : f.unit === "usd" ? big(f.value) : `${num(f.value)} ${f.unit}`}
              </p>
              <blockquote className="mt-1 text-fg">
                “{f.quote}”
                {f.url ? (
                  <>
                    {" "}
                    <a href={f.url} rel="noreferrer" target="_blank" className="text-[13px]">
                      source<span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  </>
                ) : null}
              </blockquote>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">No new verified facts.</p>
      )}
      {state.ownership.length > 0 ? (
        <p>
          <span className="font-semibold">New ownership filings:</span>{" "}
          {state.ownership.map((o) => `${shortDate(String(o.quarter_end ?? ""), true)} (filed ${shortDate(String(o.filed_at ?? ""), true)})`).join("; ")}
        </p>
      ) : null}
      {state.insiders.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {state.insiders.map((e, i) => (
            <li key={i}>
              <span className="font-semibold">Insider</span> ({shortDate(String(e.event_date ?? ""), true)}): {String(e.person ?? "")}, {String(e.kind ?? "").replace(/_/g, " ")}
              {e.shares === null || e.shares === undefined ? "" : `, ${big(Number(e.shares))} shares`}
              {e.value === null || e.value === undefined ? "" : `, ${big(Number(e.value))} ${String(e.currency ?? "")}`}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function ReviewDiff({ id, diff }: { id: string; diff: Partial<PackDiff> }) {
  const figures = Array.isArray(diff.figures) ? diff.figures : [];
  const kills = Array.isArray(diff.kill_criteria) ? diff.kill_criteria : [];
  const quarter = Array.isArray(diff.quarters) ? diff.quarters[0] : undefined;
  return (
    <div className="flex flex-col gap-4">
      {quarter ? (
        <p className="text-[13px] text-muted">
          Quarter to <Day iso={quarter.period_end} />, filed <Day iso={quarter.filed_at} />
          {diff.since ? (
            <>
              ; the thesis had seen the quarter to <Day iso={diff.since} />
            </>
          ) : null}
          .
        </p>
      ) : null}
      {figures.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="eyebrow">The quarter against the one before</h3>
          <Rows label={`Figures for review ${id}`}>
            {figures.map((f) => (
              <Row key={f.name} name={FIGURE_LABEL[f.name] ?? f.name} value={arrow(f.before, f.now, big)} end={<Change name={f.name} before={f.before} now={f.now} />} />
            ))}
          </Rows>
        </div>
      ) : null}
      {kills.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="eyebrow">Kill criteria then</h3>
          <KillRows label={`Kill criteria for review ${id}`} kills={kills} state={diff.state ?? null} />
        </div>
      ) : null}
      {diff.state ? <Changes id={id} state={diff.state} /> : null}
    </div>
  );
}
