import Link from "next/link";
import { Logo } from "@/components/logo";

export default function NotFound() {
  return (
    <main id="main" className="flex min-h-[70vh] flex-col items-center justify-center px-4 py-12 text-center">
      <Logo className="size-10" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight text-fg">Nothing here</h1>
      <p className="mt-2 max-w-md text-sm text-muted">
        That page doesn&apos;t exist, or the company or thesis it pointed to was removed.
      </p>
      <Link href="/" className="mt-6">
        Back to this week
      </Link>
    </main>
  );
}
