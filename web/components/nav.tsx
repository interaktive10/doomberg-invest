import Link from "next/link";
import { Logo } from "@/components/logo";
import { NavLinks, SearchBox } from "@/components/nav-links";
import { Button } from "@/components/ui/button";

/** The top bar: the name, the main navigation (one row under the name on a phone), the company search and Sign out. */
export function Nav({ email }: { email: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 px-4 sm:px-6">
        <Link href="/" className="order-1 flex h-12 items-center gap-2 text-sm font-semibold tracking-tight text-fg no-underline hover:text-fg">
          <Logo className="size-6" />
          Doomberg Invest
        </Link>
        <NavLinks />
        <div className="order-2 ml-auto flex items-center gap-1 sm:gap-2 lg:order-3">
          <SearchBox />
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="ghost" size="sm" title={`Signed in as ${email}`}>
              Sign out
            </Button>
          </form>
        </div>
      </div>
    </header>
  );
}
