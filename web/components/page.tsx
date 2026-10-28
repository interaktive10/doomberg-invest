import type { ReactNode } from "react";
import { Callout } from "@/components/callout";
import { cn } from "@/lib/utils";
import { countPillTone } from "@/lib/visual";

/** The width every screen, the header and the footer share: 1160 px, with a 16 px gutter on a phone. */
export const FRAME = "mx-auto w-full max-w-[1160px] px-4 md:px-8";

/** A screen: an eyebrow ("Week 42"), the h1, one line under it that leads with the answer, actions on the right; then
 * its sheets, 24 px apart. */
export function Page({
  title,
  children,
  actions,
  description,
  eyebrow,
}: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <main id="main" className={cn(FRAME, "flex flex-col gap-6 pt-3 pb-8 md:pt-4")}>
      <div className="rise flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h1 className="text-[32px] leading-[1.1] font-bold tracking-[-0.03em] text-fg md:text-[40px]">{title}</h1>
          {description ? <div className="text-[15px] text-muted md:text-[17px]">{description}</div> : null}
        </div>
        {/* min-w-0 and max-w-full: a switch wider than a phone (Candidates' four buckets) scrolls inside it */}
        {actions ? <div className="flex max-w-full min-w-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </main>
  );
}

/** A small accent pill with a count, next to a title ("To do 3"); a zero is a quiet grey one (lib/visual.ts). */
export function CountPill({ n, className }: { n: number; className?: string }) {
  return (
    <span className={cn("num inline-grid h-6 min-w-6 place-items-center rounded-full px-2 text-[13px] font-semibold", countPillTone(n), className)}>
      {n}
    </span>
  );
}

/** A titled sheet (a region landmark named by its h2 when `id` is given): an optional eyebrow, the title with an
 * optional count (left out at zero: the body says there is nothing; PR 6 final review L5-6) and one line under it,
 * `actions` on the right, then the body. `plain` drops the sheet (a heading over
 * a grid of its own sheets); `quiet` sets the title small and muted (a side panel like "Data health"). */
export function Section({
  title,
  children,
  id,
  eyebrow,
  description,
  actions,
  count,
  plain = false,
  quiet = false,
  className,
}: {
  title: ReactNode;
  children: ReactNode;
  id?: string;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  count?: number;
  plain?: boolean;
  quiet?: boolean;
  className?: string;
}) {
  return (
    <section
      className={cn("flex min-w-0 scroll-mt-24 flex-col gap-4", plain ? "gap-3" : "sheet p-5 md:p-6", className)}
      aria-labelledby={id}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <div className="flex flex-wrap items-center gap-2.5">
            <h2
              id={id}
              className={cn(quiet ? "text-[15px] font-semibold text-muted" : "text-[20px] font-bold tracking-[-0.02em] text-fg")}
            >
              {title}
            </h2>
            {count ? <CountPill n={count} /> : null}
          </div>
          {description ? <div className="text-[14px] text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** Nothing to show yet: one friendly line (and a next step, when there is one) in a dashed tile. */
export function Empty({ children, action, className }: { children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-tile border border-dashed border-line-strong px-5 py-8 text-center",
        className,
      )}
    >
      <p className="max-w-md text-[14px] text-muted">{children}</p>
      {action ? <div className="flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

/** Small print under a table or a form. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-[13px] text-subtle", className)}>{children}</p>;
}

/** A message passed back in the query string by a server action (?error= / ?ok=). The only status and alert in main. */
export function Flash({ error, ok }: { error?: string | undefined; ok?: string | undefined }) {
  return (
    <>
      {error ? (
        <Callout tone="bad" role="alert">
          {error}
        </Callout>
      ) : null}
      {ok ? (
        <Callout tone="good" role="status">
          {ok}
        </Callout>
      ) : null}
    </>
  );
}
