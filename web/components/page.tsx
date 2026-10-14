import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A screen: its h1 (with an optional line under it and actions on the right) over a hairline, then its panels. */
export function Page({
  title,
  children,
  actions,
  description,
}: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  description?: ReactNode;
}) {
  return (
    <main id="main" className="mx-auto w-full max-w-[1440px] px-4 pt-5 pb-8 sm:px-6">
      <div className="mb-3 flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-line pb-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight text-fg sm:text-2xl">{title}</h1>
          {description ? <div className="mt-1 text-[13px] text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="flex flex-col gap-3">{children}</div>
    </main>
  );
}

/** A titled panel: a header bar with the h2 (a region landmark) and `actions` on its right, then the body. */
export function Section({
  title,
  children,
  id,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  children: ReactNode;
  id?: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("min-w-0 scroll-mt-24 rounded-md border border-line bg-panel", className)} aria-labelledby={id}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-t-md border-b border-line bg-raised px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <h2 id={id} className="text-sm font-semibold tracking-tight text-fg">
            {title}
          </h2>
          {description ? <div className="mt-0.5 text-xs text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-sm border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted">{children}</p>;
}

/** Small print under a table or a form. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-xs text-subtle", className)}>{children}</p>;
}

/** A message passed back in the query string by a server action (?error= / ?ok=). The only status and alert in main. */
export function Flash({ error, ok }: { error?: string | undefined; ok?: string | undefined }) {
  return (
    <>
      {error ? (
        <p role="alert" className="rounded-sm border border-down/40 border-l-2 border-l-down bg-down/10 px-3 py-2 text-[13px] text-fg">
          {error}
        </p>
      ) : null}
      {ok ? (
        <p role="status" className="rounded-sm border border-up/40 border-l-2 border-l-up bg-up/10 px-3 py-2 text-[13px] text-fg">
          {ok}
        </p>
      ) : null}
    </>
  );
}

/** The strip of key figures at the top of a screen: Kpi cells on hairlines, two to a row on a phone. */
export function KpiRibbon({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-md border border-line bg-panel">
      <div className="-mt-px -ml-px flex flex-wrap">{children}</div>
    </div>
  );
}

const TONE = {
  up: "text-up",
  down: "text-down",
  warn: "text-warn",
  accent: "text-accent",
} as const;

/** One key figure: a caps label, the value in monospace (coloured only when it is good, bad or needs a look), an
 * optional 0–100 bar and a hint. With `href` the whole cell is a link. No role or label: it is plain text. */
export function Kpi({
  label,
  value,
  hint,
  href,
  tone,
  bar,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  href?: string;
  tone?: keyof typeof TONE;
  bar?: number | null;
}) {
  const width = typeof bar === "number" && Number.isFinite(bar) ? Math.max(0, Math.min(100, bar)) : null;
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="caps">{label}</span>
        {href ? (
          <span aria-hidden="true" className="font-mono text-[11px] text-subtle group-hover:text-accent">
            →
          </span>
        ) : null}
      </div>
      <div
        className={cn(
          "mt-1 font-mono text-xl leading-7 font-semibold tracking-tight break-words sm:text-2xl sm:leading-8",
          tone ? TONE[tone] : "text-fg",
        )}
      >
        {value}
      </div>
      {width !== null ? (
        <span aria-hidden="true" className="mt-2 block h-1 bg-line-strong">
          <span className="block h-full bg-accent" style={{ width: `${width}%` }} />
        </span>
      ) : null}
      {hint ? <div className="mt-0.5 text-xs text-muted">{hint}</div> : null}
    </>
  );
  const cell = "min-w-[9.5rem] flex-1 border-t border-l border-line px-4 py-3";
  // KpiRibbon clips its overflow (outer hairlines, rounded hover), so a link cell draws its focus ring inside itself.
  return href ? (
    <Link href={href} className={cn(cell, "group block no-underline transition-colors hover:bg-raised focus-visible:outline-offset-[-2px]")}>
      {body}
    </Link>
  ) : (
    <div className={cell}>{body}</div>
  );
}
