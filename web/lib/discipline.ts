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
const IST = 330 * 60 * 1000; // Manzoor's calendar: IST, UTC+05:30 (BRIEF §4.9: his routine runs at 06:00 IST)

/** Today's date in Manzoor's calendar: the journal form's default and the latest date an entry takes (M7 review
 * round 2: in the UTC date, today's IST date was refused between 00:00 and 05:30 IST). */
export function localToday(now: Date): string {
  return new Date(now.getTime() + IST).toISOString().slice(0, 10);
}

/** A start_position entry's date: not before the thesis started (acceptance, else the card's week) and not after
 * today; the §11.9 age is measured at the end of that date (M7 review R1-F8), or now if that is sooner, so a date
 * never adds age the thesis doesn't have yet. Returns the time to measure at, or why the date is refused. */
export function entryDateCheck(
  entryDate: string,
  acceptedAt: string | null,
  createdWeek: string,
  now: Date,
): { ok: true; at: Date } | { ok: false; message: string } {
  if (!ISO.test(entryDate)) return { ok: false, message: "The entry needs a date." };
  const start = (acceptedAt ?? `${createdWeek}T00:00:00Z`).slice(0, 10);
  if (entryDate > localToday(now)) return { ok: false, message: "A position can't start in the future." };
  if (entryDate < start) return { ok: false, message: `A position can't start before the thesis did (${start}).` };
  return { ok: true, at: new Date(Math.min(new Date(`${entryDate}T23:59:59Z`).getTime(), now.getTime())) };
}
