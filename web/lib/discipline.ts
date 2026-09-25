// BRIEF §11.9: a thesis must be >= N weeks old (default 4, Settings) before a start_position journal entry; an
// override needs a written reason. Age counts from acceptance (research -> thesis), else from the card's week.

export interface DisciplineCheck {
  ok: boolean;
  weeks: number;
  message: string;
}

const DAY = 24 * 60 * 60 * 1000;

export function thesisWeeks(acceptedAt: string | null, createdWeek: string, now: Date): number {
  const start = new Date(acceptedAt ?? `${createdWeek}T00:00:00Z`);
  return Math.floor((now.getTime() - start.getTime()) / (7 * DAY));
}

export function checkStartPosition(
  weeks: number,
  minWeeks: number,
  overrideReason: string | null | undefined,
): DisciplineCheck {
  if (weeks >= minWeeks) return { ok: true, weeks, message: "" };
  if ((overrideReason ?? "").trim().length > 0) return { ok: true, weeks, message: "override" };
  return {
    ok: false,
    weeks,
    message: `The thesis is ${weeks} week(s) old; the rule is ${minWeeks}. Write an override reason to go ahead.`,
  };
}
