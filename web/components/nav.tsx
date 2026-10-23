import Link from "next/link";
import { Logo } from "@/components/logo";
import { Dock, NavLinks, SearchBox } from "@/components/nav-links";
import { FRAME } from "@/components/page";
import { ThemeSwitch } from "@/components/theme-switch";
import type { ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/utils";

/** The app's frame: the header (the name, the main navigation as segmented pills from md up, the company search and
 * the theme button) and, on a phone, the glass dock at the bottom with the same places. One search box and one theme
 * button serve every width. Sign out sits under More. */
export function Nav({ email, theme }: { email: string; theme: ThemeMode }) {
  return (
    <>
      <header className="sticky top-0 z-30 bg-canvas/80 backdrop-blur-md">
        <div className={cn(FRAME, "flex h-16 items-center gap-3 md:h-[72px] md:gap-4")}>
          <div className="flex shrink-0 items-center md:flex-1 md:basis-0">
            {/* on a phone the wordmark alone, so the search box keeps room for its whole placeholder (PR 6 final review
                HC-2); 44 px tall either way */}
            <Link href="/" className="flex min-h-11 items-center gap-2.5 text-fg no-underline hover:text-fg">
              <Logo className="hidden size-8 sm:block" />
              <span className="text-[17px] font-bold tracking-[-0.02em]">doomberg</span>
            </Link>
          </div>
          <NavLinks email={email} />
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2 md:basis-0">
            <SearchBox className="w-full max-w-64 md:w-52 lg:w-60" />
            <ThemeSwitch initial={theme} />
          </div>
        </div>
      </header>
      <Dock email={email} />
    </>
  );
}
