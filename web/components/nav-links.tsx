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
  ["/lab", "Signal Lab"],
  ["/settings", "Settings"],
] as const;

// A tab in the bar (an accent rule under the current one) and an item in the More menu (an accent rule on its left).
// Two separate class sets, so tailwind-merge never mixes them.
const TAB = "inline-flex h-10 items-center px-3 text-[13px] font-medium whitespace-nowrap no-underline transition-colors lg:h-12";
const TAB_ON = "text-fg shadow-[inset_0_-2px_0_var(--color-accent)] hover:text-fg";
const TAB_OFF = "text-muted hover:text-fg";
const ITEM = "flex h-8 items-center rounded-sm px-2.5 text-[13px] no-underline";
const ITEM_ON = "bg-hover text-fg shadow-[inset_2px_0_0_var(--color-accent)]";
const ITEM_OFF = "text-muted hover:bg-hover hover:text-fg";

/** The main navigation: three destinations, the rest under More (a native disclosure, no script). The current screen
 * is marked (aria-current). */
export function NavLinks() {
  const path = usePathname() ?? "/";
  const current = (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`));
  const link = (href: string, label: string, menu = false) => (
    <Link
      key={href}
      href={href}
      aria-current={current(href) ? "page" : undefined}
      className={menu ? cn(ITEM, current(href) ? ITEM_ON : ITEM_OFF) : cn(TAB, current(href) ? TAB_ON : TAB_OFF)}
    >
      {label}
    </Link>
  );
  const inMore = MORE.some(([href]) => current(href));
  return (
    <nav aria-label="Main" className="order-3 flex w-full items-center lg:order-2 lg:w-auto">
      {MAIN.map(([href, label]) => link(href, label))}
      <details className="relative">
        <summary className={cn(TAB, inMore ? TAB_ON : TAB_OFF, "gap-1 list-none [&::-webkit-details-marker]:hidden")}>
          More
          <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current">
            <path d="M5.5 7.5 10 12l4.5-4.5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
        </summary>
        <div className="absolute right-0 z-40 mt-1 flex w-52 flex-col rounded-md border border-line-strong bg-raised p-1 shadow-pop lg:right-auto lg:left-0">
          {MORE.map(([href, label]) => link(href, label, true))}
        </div>
      </details>
    </nav>
  );
}
