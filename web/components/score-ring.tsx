import { ringGeometry } from "@/lib/visual";
import { cn } from "@/lib/utils";

export type ScoreKind = "evidence" | "gap";

const NAME: Record<ScoreKind, string> = { evidence: "Evidence", gap: "Gap" };
/** What each score means, in two words (the mock's captions). */
export const SCORE_HINT: Record<ScoreKind, string> = { evidence: "how sure", gap: "price behind" };

const R = 22;

/** A score as a ring that fills to its value (0-100) with the number in the middle: Evidence in the accent blue, Gap in
 * green. Read as one image ("Evidence 94 of 100"; "Gap: not scored" when there is no score). `size` is in px. */
export function ScoreRing({
  value,
  kind,
  size = 52,
  label,
  className,
}: {
  value: number | null;
  kind: ScoreKind;
  size?: number;
  label?: string;
  className?: string;
}) {
  const g = ringGeometry(value, R);
  const name = label ?? NAME[kind];
  return (
    <svg
      role="img"
      aria-label={g.shown === null ? `${name}: not scored` : `${name} ${g.shown} of 100`}
      width={size}
      height={size}
      viewBox="0 0 52 52"
      className={cn("shrink-0", className)}
    >
      <circle cx="26" cy="26" r={R} fill="none" strokeWidth="5" className="stroke-track" />
      {g.length > 0 ? (
        <circle
          cx="26"
          cy="26"
          r={R}
          fill="none"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${g.length} ${g.circumference}`}
          transform="rotate(-90 26 26)"
          className={cn("ring-fill", kind === "evidence" ? "stroke-accent" : "stroke-gap")}
        />
      ) : null}
      <text x="26" y="31" textAnchor="middle" fontSize="15" fontWeight="700" className="num fill-fg">
        {g.shown === null ? "–" : g.shown}
      </text>
    </svg>
  );
}

/** A score ring in a tile with its name and what it means ("Evidence / how sure"), as on a Candidates card. The ring
 * already says its name ("Evidence 73 of 100"), so the caption's name is hidden from screen readers and only what it
 * means is read after it. */
export function ScoreTile({
  value,
  kind,
  hint = SCORE_HINT[kind],
  size = 48,
  className,
}: {
  value: number | null;
  kind: ScoreKind;
  hint?: string;
  size?: number;
  className?: string;
}) {
  return (
    <div className={cn("tile flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5", className)}>
      <ScoreRing value={value} kind={kind} size={size} />
      <div className="flex min-w-0 flex-col">
        <span aria-hidden="true" className="text-[13px] font-semibold text-fg">
          {NAME[kind]}
        </span>
        <span className="text-[12px] text-subtle">{hint}</span>
      </div>
    </div>
  );
}
