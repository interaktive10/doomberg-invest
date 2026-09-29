import type { ReactNode } from "react";

export function Page({ title, children, actions }: { title: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <main id="main" className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {actions ? <div className="ml-auto flex flex-wrap gap-2">{actions}</div> : null}
      </div>
      {children}
    </main>
  );
}

export function Section({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  return (
    <section className="mt-8" aria-labelledby={id}>
      <h2 id={id} className="mb-2 text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-gray-700">{children}</p>;
}

/** A message passed back in the query string by a server action (?error= / ?ok=). */
export function Flash({ error, ok }: { error?: string | undefined; ok?: string | undefined }) {
  return (
    <>
      {error ? (
        <p role="alert" className="mb-4 rounded-md border border-red-700 bg-red-50 p-3 text-sm">
          {error}
        </p>
      ) : null}
      {ok ? (
        <p role="status" className="mb-4 rounded-md border border-green-800 bg-green-50 p-3 text-sm">
          {ok}
        </p>
      ) : null}
    </>
  );
}
