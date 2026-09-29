import { requireUser } from "@/lib/auth";
import { toCsv } from "@/lib/csv";
import { screen } from "@/lib/data";
import { CSV_COLUMNS, csvRow, specFromForm, type ScreenSpec } from "@/lib/screener";

// BRIEF §6 Screener CSV export (personal use): the same spec as the page's query string, up to 2,000 rows.
export async function GET(request: Request): Promise<Response> {
  await requireUser();
  const params = new URL(request.url).searchParams;
  let spec: ScreenSpec;
  try {
    spec = specFromForm(params);
  } catch {
    return new Response("That screen isn't valid.", { status: 400 });
  }
  const rows = await screen({ ...spec, limit: spec.limit ?? 2000 });
  const day = new Date().toISOString().slice(0, 10);
  return new Response(toCsv(CSV_COLUMNS, rows.map(csvRow)), {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="doomberg-screen-${day}.csv"`,
      "cache-control": "no-store",
    },
  });
}
