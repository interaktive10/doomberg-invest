import Link from "next/link";

// A company or thesis id that doesn't exist (the pages call notFound()): the message sits inside the app's frame, so
// the navigation stays. Unknown URLs get app/not-found.tsx.
export default function NotFound() {
  return (
    <main id="main" className="mx-auto w-full max-w-[1440px] px-4 py-16 text-center sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-fg">Nothing here</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        That company or thesis doesn&apos;t exist, or it was removed.
      </p>
      <Link href="/" className="mt-6 inline-block">
        Back to this week
      </Link>
    </main>
  );
}
