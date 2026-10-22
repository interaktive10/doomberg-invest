"use client";

import Link from "next/link";
import { Icon } from "@/components/icons";
import { FRAME } from "@/components/page";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// A screen that failed to load (a database timeout, a bad row): say so and offer a retry instead of a blank page. The
// server logs the error; `digest` ties this page to that log line.
export default function ScreenError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main" className={cn(FRAME, "pt-6 pb-8 md:pt-10")}>
      <div className="sheet flex max-w-xl flex-col gap-4 p-6 md:p-7">
        <span aria-hidden="true" className="grid size-11 place-items-center rounded-full bg-down/10 text-down">
          <Icon name="alert" className="size-5" />
        </span>
        <div className="flex flex-col gap-1.5">
          <h1 className="text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">This screen couldn&apos;t load</h1>
          <p className="text-[15px] text-muted">A passing database or network hiccup, most likely. Trying again usually works.</p>
          {error.digest ? <p className="num text-[13px] text-subtle">Reference: {error.digest}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => reset()}>Try again</Button>
          <Link href="/" className={buttonVariants({ variant: "secondary" })}>
            Back to this week
          </Link>
        </div>
      </div>
    </main>
  );
}
