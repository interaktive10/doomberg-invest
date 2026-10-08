import Link from "next/link";
import { Logo } from "@/components/logo";
import { NavLinks } from "@/components/nav-links";
import { Button } from "@/components/ui/button";

export function Nav({ email }: { email: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-gray-200/70 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
        <Link href="/" className="order-1 flex items-center gap-2.5 font-semibold tracking-tight text-gray-900 no-underline hover:text-gray-900">
          <Logo />
          Doomberg Invest
        </Link>
        <NavLinks />
        <form action="/auth/signout" method="post" className="order-2 ml-auto lg:order-3">
          <Button type="submit" variant="ghost" size="sm" title={`Signed in as ${email}`}>
            Sign out
          </Button>
        </form>
      </div>
    </header>
  );
}
