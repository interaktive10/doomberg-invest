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
    <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-8 pb-6 sm:pt-12">
      <div className="mb-8 flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900">{title}</h1>
          {description ? <div className="mt-2 text-[15px] text-gray-600">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="flex flex-col gap-6">{children}</div>
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
      className={cn("scroll-mt-20 rounded-2xl border border-gray-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04)] sm:p-6", className)}
      aria-labelledby={id}
    >
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <h2 id={id} className="text-base font-semibold tracking-tight text-gray-900">
            {title}
          </h2>
          {description ? <div className="mt-1 text-sm text-gray-600">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-gray-300 bg-gray-50/60 px-4 py-8 text-center text-sm text-gray-600">{children}</p>;
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
      <div className="text-sm font-medium text-gray-600">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums">{value}</div>
      {hint ? <div className="mt-1 text-xs text-gray-600">{hint}</div> : null}
    </>
  );
  const box = "block rounded-2xl border border-gray-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04)]";
  return href ? (
    <Link href={href} className={cn(box, "no-underline transition-shadow hover:border-gray-300 hover:shadow-md")}>
      {body}
    </Link>
  ) : (
    <div className={box}>{body}</div>
  );
}
