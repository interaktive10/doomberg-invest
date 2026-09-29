import Link from "next/link";

// A company or thesis id that doesn't exist (the pages call notFound()): the message sits inside the app's frame, so
// the navigation stays. Unknown URLs get app/not-found.tsx.
export default function NotFound() {
  return (
    <main id="main" className="mx-auto w-full max-w-6xl px-4 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Nothing here</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-gray-700">
        That company or thesis doesn&apos;t exist, or it was removed.
      </p>
      <Link href="/" className="mt-6 inline-block">
        Back to this week
      </Link>
    </main>
  );
}
