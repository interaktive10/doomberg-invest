"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

// A screen that failed to load (a database timeout, a bad row): say so and offer a retry instead of a blank page. The
// server logs the error; `digest` ties this page to that log line.
export default function ScreenError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main" className="mx-auto w-full max-w-6xl px-4 py-10">
      <div className="max-w-xl rounded-xl border border-red-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight">This screen couldn&apos;t load</h1>
        <p className="mt-2 text-sm text-gray-700">
          Reading the data failed. It is often a passing database or network hiccup, so trying again usually works.
        </p>
        {error.digest ? <p className="mt-2 text-xs text-gray-700">Reference: {error.digest}</p> : null}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={() => reset()}>Try again</Button>
          <Link href="/">Back to this week</Link>
        </div>
      </div>
    </main>
  );
}
