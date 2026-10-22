import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { cn } from "@/lib/utils";

/** The place for explanations: a small "Why" (or "Details") pill that opens the longer text under it, so the page shows
 * the answer and keeps the reasoning one tap away. A native disclosure: works without script, keyboard and screen
 * readers included. */
export function Disclosure({
  summary = "Why",
  children,
  open,
  className,
}: {
  summary?: ReactNode;
  children: ReactNode;
  open?: boolean;
  className?: string;
}) {
  return (
    <details open={open} className={cn("group min-w-0", className)}>
      <summary className="-ml-3 inline-flex min-h-11 list-none items-center gap-1 rounded-full px-3 text-[13px] font-semibold text-accent transition-colors duration-150 hover:bg-hover md:min-h-9 [&::-webkit-details-marker]:hidden">
        {summary}
        <Icon name="chevron-down" className="transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="mt-2 text-[14px] text-muted">{children}</div>
    </details>
  );
}
