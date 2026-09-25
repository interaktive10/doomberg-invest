import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { big, num } from "@/lib/format";
import type { KillSnapshot, PackDiff, StateDiff } from "@/lib/reviews";

// A review's pack diff (BRIEF §4.9 "the pack diff since the last review"; M7 review R1-F4): the quarter's key figures
// against the quarter before, the kill criteria as they stood, and what changed since the last review (or the card):
// signals and red flags, context, new facts, ownership rows and insider events.

const FIGURE_LABEL: Record<string, string> = {
  revenue: "Revenue",
  op_income: "Operating income",
  net_income: "Net income",
  cfo: "Cash from operations",
  rpo: "RPO",
  diluted_shares: "Diluted shares",
};

function arrow(before: number | null, now: number | null, fmt: (v: number | null) => string): string {
  return `${fmt(before)} → ${fmt(now)}`;
}

function ratio(v: number | null): string {
  return v === null ? "n/a" : num(v, 4);
}

function list(ids: readonly string[]): string {
  return ids.length === 0 ? "none" : ids.join(", ");
}

function KillTable({ label, kills, state }: { label: string; kills: readonly KillSnapshot[]; state: StateDiff | null }) {
  const before = new Map((state?.kill ?? []).map((k) => [k.metric, k.before]));
  return (
    <Table label={label}>
      <TableHeader>
        <TableRow>
          <TableHead>Kill criterion</TableHead>
          <TableHead>Condition</TableHead>
          <TableHead>Value (before → now)</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {kills.map((k) => (
          <TableRow key={k.metric}>
            <TableCell>
              <code>{k.metric}</code>
            </TableCell>
            <TableCell>
              {k.operator} {k.threshold ?? ""}
            </TableCell>
            <TableCell>{arrow(before.get(k.metric) ?? null, k.last_value, ratio)}</TableCell>
            <TableCell>{k.status}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Changes({ id, state }: { id: string; state: StateDiff }) {
  const since = state.since ? `since ${state.since}` : "since the card";
  return (
    <div className="mt-3 flex flex-col gap-2 text-sm">
      <h3 className="font-semibold">What changed {since}</h3>
      <p>
        Signals: started {list(state.signals.fired)}; stopped {list(state.signals.dropped)}. Red flags: started{" "}
        {list(state.red_flags.fired)}; stopped {list(state.red_flags.dropped)}.
      </p>
      {state.context.length > 0 ? (
        <Table label={`Context for review ${id}`}>
          <TableHeader>
            <TableRow>
              <TableHead>Context</TableHead>
              <TableHead>Before → now</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {state.context.map((c) => (
              <TableRow key={c.id}>
                <TableCell>{c.id}</TableCell>
                <TableCell>{arrow(c.before, c.now, ratio)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      {state.facts.length > 0 ? (
        <ul className="list-disc pl-5">
          {state.facts.map((f) => (
            <li key={f.id}>
              New fact (as of {f.as_of}{f.published_at ? `, published ${f.published_at.slice(0, 10)}` : ""}): {f.subject} {f.value === null ? "" : f.unit === "usd" ? big(f.value) : `${num(f.value)} ${f.unit}`} — “{f.quote}”
              {f.url ? (
                <>
                  {" "}
                  <a href={f.url}>source</a>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p>No new verified facts.</p>
      )}
      {state.ownership.length > 0 ? (
        <p>
          New ownership filings:{" "}
          {state.ownership.map((o) => `${String(o.quarter_end ?? "")} (filed ${String(o.filed_at ?? "").slice(0, 10)})`).join("; ")}
        </p>
      ) : null}
      {state.insiders.length > 0 ? (
        <ul className="list-disc pl-5">
          {state.insiders.map((e, i) => (
            <li key={i}>
              Insider ({String(e.event_date ?? "")}): {String(e.person ?? "")}, {String(e.kind ?? "")}
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
    <div className="flex flex-col gap-2">
      {quarter ? (
        <p className="text-sm">
          Quarter {quarter.period_end}, filed {quarter.filed_at.slice(0, 10)}
          {diff.since ? `; the thesis had seen ${diff.since}` : ""}.
        </p>
      ) : null}
      {figures.length > 0 ? (
        <Table label={`Figures for review ${id}`}>
          <TableHeader>
            <TableRow>
              <TableHead>Figure</TableHead>
              <TableHead>Quarter before → this quarter</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {figures.map((f) => (
              <TableRow key={f.name}>
                <TableCell>{FIGURE_LABEL[f.name] ?? f.name}</TableCell>
                <TableCell>{arrow(f.before, f.now, big)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      {kills.length > 0 ? <KillTable label={`Kill criteria for review ${id}`} kills={kills} state={diff.state ?? null} /> : null}
      {diff.state ? <Changes id={id} state={diff.state} /> : null}
    </div>
  );
}
