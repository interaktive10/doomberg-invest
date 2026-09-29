// Shown while a screen's data loads (a server render reads Supabase first): the frame stays, the content pulses. No
// status role or h1 here: the screen's own flash message and heading are what tests and screen readers wait for.
export default function Loading() {
  return (
    <main id="main" aria-busy="true" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-4 sm:pt-8">
      <p className="sr-only">Loading…</p>
      <div className="h-8 w-56 animate-pulse rounded-md bg-gray-200" />
      <div className="mt-2 h-4 w-80 max-w-full animate-pulse rounded bg-gray-200" />
      {[0, 1].map((i) => (
        <div key={i} className="mt-5 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="h-5 w-40 animate-pulse rounded bg-gray-200" />
          <div className="mt-4 space-y-2">
            <div className="h-4 w-full animate-pulse rounded bg-gray-100" />
            <div className="h-4 w-11/12 animate-pulse rounded bg-gray-100" />
            <div className="h-4 w-4/5 animate-pulse rounded bg-gray-100" />
          </div>
        </div>
      ))}
    </main>
  );
}
