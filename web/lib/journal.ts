// A thesis's journal entries in order (the Journal page is gone: docs/SPEC_ISSUES.md 69; a thesis's entries are on its
// page). Pure, so tests/journal.test.ts covers it. The journal and post-mortems are never sent to any LLM.

/** Journal entries newest first by the date each one is about (entry_date, which can be set back), then by when it was
 * written, so the list matches the "Newest first" it says (PR 6 final review EYE-13). */
export function byEntryDate<T extends { entry_date: string; created_at: string }>(xs: readonly T[]): T[] {
  return [...xs].sort((a, b) => b.entry_date.localeCompare(a.entry_date) || b.created_at.localeCompare(a.created_at));
}
