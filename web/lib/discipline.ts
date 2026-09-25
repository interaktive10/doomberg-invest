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

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** A start_position entry's date: not before the thesis started (acceptance, else the card's week) and not after
 * today; the §11.9 age is measured at that date, not when the entry is typed in (M7 review R1-F8). Returns the date
 * to measure at, or why the date is refused. */
export function entryDateCheck(
  entryDate: string,
  acceptedAt: string | null,
  createdWeek: string,
  now: Date,
): { ok: true; at: Date } | { ok: false; message: string } {
  if (!ISO.test(entryDate)) return { ok: false, message: "The entry needs a date." };
  const start = (acceptedAt ?? `${createdWeek}T00:00:00Z`).slice(0, 10);
  const today = now.toISOString().slice(0, 10);
  if (entryDate > today) return { ok: false, message: "A position can't start in the future." };
  if (entryDate < start) return { ok: false, message: `A position can't start before the thesis did (${start}).` };
  return { ok: true, at: new Date(`${entryDate}T23:59:59Z`) };
}
