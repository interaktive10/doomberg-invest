import Link from "next/link";
import type { ReactNode } from "react";
import { LinkPending } from "@/components/link-pending";
import { CountPill } from "@/components/page";
import { cn } from "@/lib/utils";

// The segmented pill (Curator's): a grey track with the current choice lifted onto a white (in dark, a lighter grey:
// 1.5:1 against the track, tests/palette.test.ts) thumb. The desktop header's main navigation
// (components/nav-links.tsx) and a screen's own switch (Candidates' buckets) share these classes, so they look alike.
// 44 px tall on a phone, 40 px from md up.
export const SEG_TRACK = "items-center gap-1 rounded-full bg-track p-1";
export const SEG_PILL =
  "inline-flex h-11 shrink-0 items-center gap-2 rounded-full px-4 text-[14px] font-medium whitespace-nowrap no-underline transition-colors duration-200 md:h-10";
export const SEG_ON = "seg-on text-fg hover:text-fg";
export const SEG_OFF = "text-muted hover:text-fg";

export interface Segment {
  href: string;
  label: ReactNode;
  /** a count after the label, as a small accent pill ("On the board 3") */
  count?: number;
  current?: boolean;
}

/** A switch between views of one screen, as links (each view has its own URL, so it works without script): one
 * segmented pill, the current view marked (aria-current). On a phone it scrolls sideways rather than wrap. */
export function Segmented({ label, items, className }: { label: string; items: readonly Segment[]; className?: string }) {
  return (
    <div role="group" aria-label={label} className={cn(SEG_TRACK, "inline-flex max-w-full overflow-x-auto", className)}>
      {items.map((s) => (
        <Link key={s.href} href={s.href} aria-current={s.current ? "page" : undefined} className={cn(SEG_PILL, s.current ? SEG_ON : SEG_OFF)}>
          {s.label}
          {s.count !== undefined ? <CountPill n={s.count} className="h-5 min-w-5 px-1.5 text-[12px]" /> : null}
          <LinkPending />
        </Link>
      ))}
    </div>
  );
}
