// PostgREST returns at most max_rows rows per request (supabase/config.toml max_rows = 1000, Supabase's default), so a
// list that can be longer is read a page at a time (M7 review R1-F12). A page shorter than asked for can be max_rows
// capping it, so reading stops only at an empty page or at `limit`.

export const PAGE_ROWS = 1000;

type Page = PromiseLike<{ data: unknown; error: { message: string } | null }>;

export async function allPages<T>(fetchPage: (from: number, to: number) => Page, limit: number, size = PAGE_ROWS): Promise<T[]> {
  const out: T[] = [];
  while (out.length < limit) {
    const from = out.length;
    const res = await fetchPage(from, Math.min(limit, from + size) - 1);
    if (res.error) throw new Error(res.error.message);
    const rows = (res.data ?? []) as T[];
    if (rows.length === 0) break;
    out.push(...rows.slice(0, limit - from));
  }
  return out;
}
