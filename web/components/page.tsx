import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A screen: its h1 (with an optional line under it and actions on the right), then its sections. */
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
    <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-4 sm:pt-8">
      <div className="mb-5 flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">{title}</h1>
          {description ? <div className="mt-1.5 text-sm text-gray-700">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </main>
  );
}

/** A titled panel. The h2 names the section (a region landmark); `actions` sit on the right of the title. */
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
    <section
      className={cn("scroll-mt-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5", className)}
      aria-labelledby={id}
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <h2 id={id} className="text-base font-semibold text-gray-900">
            {title}
          </h2>
          {description ? <div className="mt-0.5 text-sm text-gray-700">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-center text-sm text-gray-700">{children}</p>;
}

/** Small print under a table or a form. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-xs text-gray-700", className)}>{children}</p>;
}

/** A message passed back in the query string by a server action (?error= / ?ok=). */
export function Flash({ error, ok }: { error?: string | undefined; ok?: string | undefined }) {
  return (
    <>
      {error ? (
        <p role="alert" className="rounded-lg border border-red-200 border-l-4 border-l-red-700 bg-red-50 px-4 py-3 text-sm text-red-950">
          {error}
        </p>
      ) : null}
      {ok ? (
        <p role="status" className="rounded-lg border border-green-200 border-l-4 border-l-green-700 bg-green-50 px-4 py-3 text-sm text-green-950">
          {ok}
        </p>
      ) : null}
    </>
  );
}

/** A labelled number for a summary row (Home, the Company page). */
export function Stat({ label, value, hint, href }: { label: string; value: ReactNode; hint?: ReactNode; href?: string }) {
  const body = (
    <>
      <div className="text-xs font-medium tracking-wide text-gray-700 uppercase">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-gray-900 tabular-nums">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-gray-700">{hint}</div> : null}
    </>
  );
  const box = "block rounded-xl border border-gray-200 bg-white p-4 shadow-sm";
  return href ? (
    <Link href={href} className={cn(box, "no-underline transition-colors hover:border-blue-300 hover:bg-blue-50/40")}>
      {body}
    </Link>
  ) : (
    <div className={box}>{body}</div>
  );
}
