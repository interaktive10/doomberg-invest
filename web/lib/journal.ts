import type { Postmortem } from "@/lib/data";

// The Journal drawn (overhaul PR 6): one line that counts what is there, a post-mortem tally of theses called right,
// and the post-mortem's signals note as text. Pure, so tests/journal.test.ts covers it. Everything here stays in the
// page: the journal and post-mortems are never sent to any LLM.

/** The Journal's line under its title. */
export function journalLine(entries: number, postmortems: number): string {
  if (entries === 0 && postmortems === 0) return "Nothing written yet. What you write here stays private.";
  const e = `${entries.toLocaleString("en-US")} ${entries === 1 ? "entry" : "entries"}`;
  const p = `${postmortems.toLocaleString("en-US")} ${postmortems === 1 ? "post-mortem" : "post-mortems"}`;
  return `${e} and ${p}, all private.`;
}

/** Journal entries newest first by the date each one is about (entry_date, which can be set back), then by when it was
 * written, so the list matches the "Newest first" it says (PR 6 final review EYE-13). */
export function byEntryDate<T extends { entry_date: string; created_at: string }>(xs: readonly T[]): T[] {
  return [...xs].sort((a, b) => b.entry_date.localeCompare(a.entry_date) || b.created_at.localeCompare(a.created_at));
}

/** How the closed theses' post-mortems judged them. */
export function trackRecord(pms: readonly Pick<Postmortem, "thesis_right">[]): { right: number; wrong: number; unclear: number } {
  const out = { right: 0, wrong: 0, unclear: 0 };
  for (const p of pms) {
    if (p.thesis_right === true) out.right += 1;
    else if (p.thesis_right === false) out.wrong += 1;
    else out.unclear += 1;
  }
  return out;
}

/** The record in words: "1 of 2 called right", or null before the first post-mortem. */
export function recordLine(r: { right: number; wrong: number; unclear: number }): string | null {
  const total = r.right + r.wrong + r.unclear;
  return total === 0 ? null : `${r.right} of ${total} called right`;
}

/** A post-mortem's "what the signals said" (signals_right.note) as text; "" when there is none. */
export function signalsNote(v: Postmortem["signals_right"]): string {
  const note = v?.note;
  return typeof note === "string" ? note.trim() : note === null || note === undefined ? "" : String(note);
}
