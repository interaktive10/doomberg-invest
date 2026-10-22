import Link from "next/link";
import { FRAME } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// A company or thesis id that doesn't exist (the pages call notFound()): the message sits inside the app's frame, so
// the navigation stays. Unknown URLs get app/not-found.tsx.
export default function NotFound() {
  return (
    <main id="main" className={cn(FRAME, "pt-6 pb-8 md:pt-10")}>
      <div className="sheet mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-10 text-center">
        <h1 className="text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">Nothing here</h1>
        <p className="text-[15px] text-muted">That company or thesis doesn&apos;t exist, or it was removed.</p>
        <Link href="/" className={cn(buttonVariants(), "mt-2")}>
          Back to this week
        </Link>
      </div>
    </main>
  );
}
