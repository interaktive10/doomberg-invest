import Link from "next/link";
import { Logo } from "@/components/logo";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// An unknown URL, outside the app's shell (a signed-out visit sees it too): the mark, one line and the way back.
export default function NotFound() {
  return (
    <main id="main" className="flex min-h-[70dvh] flex-col items-center justify-center px-4 py-12 text-center">
      <div className="sheet rise flex w-full max-w-md flex-col items-center gap-3 px-6 py-10">
        <Logo className="size-10" />
        <h1 className="mt-1 text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">Nothing here</h1>
        <p className="text-[15px] text-muted">That page doesn&apos;t exist, or the company or thesis it pointed to was removed.</p>
        <Link href="/" className={cn(buttonVariants(), "mt-2")}>
          Back to this week
        </Link>
      </div>
      <p className="mt-6 text-[12px] text-subtle">Research only. No orders, no price alerts.</p>
    </main>
  );
}
