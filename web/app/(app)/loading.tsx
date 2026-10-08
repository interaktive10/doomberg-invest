// Shown at once while a screen's data loads, so a click answers immediately.
export default function Loading() {
  return (
    <main id="main" aria-busy="true" className="mx-auto w-full max-w-6xl animate-pulse px-4 pt-8 pb-6 sm:pt-12">
      <span className="sr-only">Loading…</span>
      <div className="h-8 w-56 rounded-lg bg-gray-200" />
      <div className="mt-3 h-4 w-80 max-w-full rounded bg-gray-200" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-36 rounded-2xl border border-gray-200/80 bg-white" />
        ))}
      </div>
    </main>
  );
}
