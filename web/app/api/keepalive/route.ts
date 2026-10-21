import { NextResponse } from "next/server";
import { db } from "@/lib/supabase/admin";

// BRIEF §2.9 keep-alive: Supabase's free plan pauses a project after 7 days without activity. The daily GitHub Actions
// run kept it awake until Actions stopped on the billing limit (2026-10-20); Vercel's free cron (vercel.json) calls this
// once a day as well, so the database stays up whatever Actions does. One one-row read; nothing from the database is
// returned, so the route needs no sign-in (middleware PUBLIC).
export const dynamic = "force-dynamic";

export async function GET() {
  const { error } = await db().from("companies").select("id").limit(1);
  return new NextResponse(JSON.stringify({ ok: !error }), {
    status: error ? 503 : 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
