"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const MAIN = [
  ["/", "This week"],
  ["/candidates", "Candidates"],
  ["/theses", "Theses"],
] as const;

const MORE = [
  ["/journal", "Journal"],
  ["/screener", "Screener"],
  ["/capex", "Capex Desk"],
  ["/lab", "Signal Lab"],
  ["/settings", "Settings"],
] as const;

/** The main navigation: three destinations, the rest under More (a native disclosure, no script). The current screen
 * is marked (aria-current). */
export function NavLinks() {
  const path = usePathname() ?? "/";
  const current = (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`));
  const link = (href: string, label: string, extra = "") => (
    <Link
      key={href}
      href={href}
      aria-current={current(href) ? "page" : undefined}
      className={cn(
        "rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap no-underline transition-colors",
        current(href) ? "bg-gray-100 text-gray-900 hover:text-gray-900" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
        extra,
      )}
    >
      {label}
    </Link>
  );
  const inMore = MORE.some(([href]) => current(href));
  return (
    <nav aria-label="Main" className="order-3 flex w-full items-center gap-1 lg:order-2 lg:w-auto">
      {MAIN.map(([href, label]) => link(href, label))}
      <details className="relative">
        <summary
          className={cn(
            "flex cursor-pointer list-none items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors [&::-webkit-details-marker]:hidden",
            inMore ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
          )}
        >
          More
          <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current">
            <path d="M5.5 7.5 10 12l4.5-4.5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
        </summary>
        <div className="absolute right-0 z-40 mt-2 flex w-48 flex-col gap-0.5 rounded-xl border border-gray-200 bg-white p-1.5 shadow-lg lg:left-0 lg:right-auto">
          {MORE.map(([href, label]) => link(href, label, "block"))}
        </div>
      </details>
    </nav>
  );
}
