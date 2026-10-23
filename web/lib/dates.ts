// Dates as the screens say them (overhaul PR 6): "Sep 18", "Fri, Sep 18", "Week 38 · Sep 14–18". ISO dates in, UTC
// throughout: the pipeline's weeks end on a Friday (scores.week_end) and its week label is the ISO week
// (pipeline/thesis/evidence_pack.py week_label). Pure, so tests/dates.test.ts covers it. A string that isn't an ISO
// date comes back as it is, so a bad value shows instead of "Invalid Date".

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const DAY = 86_400_000;

/** "2026-09-18" (or a timestamp starting with one) as a UTC midnight; null when it isn't a real date. */
export function utcDay(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso.trim());
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = new Date(Date.UTC(y, mo - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === mo - 1 && t.getUTCDate() === d ? t : null;
}

/** "Sep 18" ("Sep 18, 2026" with the year). */
export function shortDate(iso: string, year = false): string {
  const t = utcDay(iso);
  if (t === null) return iso;
  const s = `${MONTHS[t.getUTCMonth()]} ${t.getUTCDate()}`;
  return year ? `${s}, ${t.getUTCFullYear()}` : s;
}

/** The calendar quarter a period ends in, as the charts label it: "2023-09-30" -> "Q3 ’23". A period that ends in a
 * quarter's first week counts as the quarter before, so a 52/53-week filer's quarters ("2023-07-01", "2023-09-30")
 * never share a label and "2026-07-04" is Q2 ’26 (PR 6 final review C5). */
export function quarterLabel(iso: string): string {
  const t = utcDay(iso);
  if (t === null) return iso;
  const q = new Date(t.getTime() - 7 * DAY);
  return `Q${Math.floor(q.getUTCMonth() / 3) + 1} ’${String(q.getUTCFullYear() % 100).padStart(2, "0")}`;
}

/** "Fri, Sep 18". */
export function dayDate(iso: string): string {
  const t = utcDay(iso);
  return t === null ? iso : `${DAYS[t.getUTCDay()]}, ${shortDate(iso)}`;
}

/** The ISO week number (1-53) of the date, as the digest's title counts it ("2026-W38"). */
export function isoWeek(iso: string): number | null {
  const t = utcDay(iso);
  if (t === null) return null;
  const thursday = (d: Date) => new Date(d.getTime() + (3 - ((d.getUTCDay() + 6) % 7)) * DAY);
  const th = thursday(t);
  const first = thursday(new Date(Date.UTC(th.getUTCFullYear(), 0, 4)));
  return 1 + Math.round((th.getTime() - first.getTime()) / (7 * DAY));
}

/** The working week a week end closes, Monday to that day: "Sep 14–18", or "Aug 31 – Sep 4" across a month. */
export function weekSpan(weekEnd: string): string {
  const t = utcDay(weekEnd);
  if (t === null) return weekEnd;
  const start = new Date(t.getTime() - ((t.getUTCDay() + 6) % 7) * DAY);
  if (start.getUTCMonth() === t.getUTCMonth()) return `${MONTHS[t.getUTCMonth()]} ${start.getUTCDate()}–${t.getUTCDate()}`;
  return `${MONTHS[start.getUTCMonth()]} ${start.getUTCDate()} – ${MONTHS[t.getUTCMonth()]} ${t.getUTCDate()}`;
}

/** A screen's eyebrow for a scored week: "Week 38 · Sep 14–18" (just "Week 38" when `span` is false). */
export function weekEyebrow(weekEnd: string, span = true): string {
  const w = isoWeek(weekEnd);
  if (w === null) return weekEnd;
  return span ? `Week ${w} · ${weekSpan(weekEnd)}` : `Week ${w}`;
}
