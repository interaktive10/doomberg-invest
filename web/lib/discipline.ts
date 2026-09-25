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

/** An instant's date in Manzoor's calendar (IST). */
export function istDate(at: Date): string {
  return new Date(at.getTime() + IST).toISOString().slice(0, 10);
}

/** Today's date in Manzoor's calendar: the journal forms' default and the latest date an entry takes (M7 review
 * round 2: in the UTC date, today's IST date was refused between 00:00 and 05:30 IST). */
export function localToday(now: Date): string {
  return istDate(now);
}

/** The last second of an IST date (23:59:59 IST, which is 18:29:59Z). */
export function endOfIstDay(date: string): Date {
  return new Date(new Date(`${date}T23:59:59Z`).getTime() - IST);
}

/** A start_position entry's date, an IST date like every journal date: not before the thesis started (the IST date of
 * its acceptance, else the card's week) and not after today; the §11.9 age is measured at the end of that IST date
 * (M7 review R1-F8, R3-F2), or now if that is sooner, so a date never adds age the thesis doesn't have yet. Returns the
 * time to measure at, or why the date is refused. */
export function entryDateCheck(
  entryDate: string,
  acceptedAt: string | null,
  createdWeek: string,
  now: Date,
): { ok: true; at: Date } | { ok: false; message: string } {
  if (!ISO.test(entryDate)) return { ok: false, message: "The entry needs a date." };
  const start = acceptedAt === null ? createdWeek : istDate(new Date(acceptedAt));
  if (entryDate > localToday(now)) return { ok: false, message: "A position can't start in the future." };
  if (entryDate < start) return { ok: false, message: `A position can't start before the thesis did (${start}).` };
  return { ok: true, at: new Date(Math.min(endOfIstDay(entryDate).getTime(), now.getTime())) };
}
