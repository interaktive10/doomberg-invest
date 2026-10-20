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
