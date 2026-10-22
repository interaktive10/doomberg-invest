"use client";

import Link from "next/link";
import { Icon } from "@/components/icons";
import { FRAME } from "@/components/page";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// A screen that failed to load (a database timeout, a bad row): say so and offer a retry instead of a blank page. The
// server logs the error; `digest` ties this page to that log line. Drawn like the not-found sheet (overhaul PR 6).
export default function ScreenError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main" className={cn(FRAME, "pt-6 pb-8 md:pt-10")}>
      <div className="sheet rise mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-10 text-center">
        <span aria-hidden="true" className="grid size-12 place-items-center rounded-full bg-down/10 text-down">
          <Icon name="alert" className="size-5" />
        </span>
        <h1 className="text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">This screen couldn&apos;t load</h1>
        <p className="text-[15px] text-muted">A passing database or network hiccup, most likely. Trying again usually works.</p>
        {error.digest ? <p className="num text-[13px] text-subtle">Reference: {error.digest}</p> : null}
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          <Button onClick={() => reset()}>Try again</Button>
          <Link href="/" className={buttonVariants({ variant: "secondary" })}>
            Back to this week
          </Link>
        </div>
      </div>
    </main>
  );
}
