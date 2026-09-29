"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  ["/", "Home"],
  ["/candidates", "Candidates"],
  ["/theses", "Theses"],
  ["/journal", "Journal"],
  ["/screener", "Screener"],
  ["/capex", "Capex Desk"],
  ["/lab", "Signal Lab"],
  ["/settings", "Settings"],
] as const;

/** The main navigation: the current screen is marked (aria-current). Four to a row on a phone, a row of their own on a
 * tablet, next to the name from lg. */
export function NavLinks() {
  const path = usePathname() ?? "/";
  const current = (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`));
  return (
    <nav aria-label="Main" className="order-3 grid w-full grid-cols-4 gap-1 sm:flex sm:flex-wrap sm:gap-0.5 lg:order-2 lg:w-auto">
      {LINKS.map(([href, label]) => (
        <Link
          key={href}
          href={href}
          aria-current={current(href) ? "page" : undefined}
          className={cn(
            "rounded-md px-1 py-1.5 text-center text-[13px] font-medium no-underline transition-colors sm:px-2.5 sm:text-sm",
            current(href) ? "bg-gray-900 text-white hover:text-white" : "text-gray-700 hover:bg-gray-100 hover:text-gray-900",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
