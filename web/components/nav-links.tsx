"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { Icon } from "@/components/icons";
import { SEG_OFF as PILL_OFF, SEG_ON as PILL_ON, SEG_PILL as PILL, SEG_TRACK } from "@/components/segmented";
import { inMore, isCurrent, MAIN, MORE } from "@/lib/nav";
import { SEARCH_MAX, typingIn } from "@/lib/search";
import { cn } from "@/lib/utils";

// The desktop header's segmented pills (components/segmented.tsx: the current one lifts onto a white thumb) and the
// phone's glass dock (the current tab on a soft fill). Separate class sets, so tailwind-merge never mixes them.
const TAB =
  "flex h-14 w-full min-w-0 flex-col items-center justify-center gap-[3px] rounded-full text-[11px] leading-none font-semibold no-underline transition-colors duration-200";
const TAB_ON = "bg-fg/10 text-fg hover:text-fg";
const TAB_OFF = "text-muted hover:text-fg";
const ITEM = "flex h-11 w-full items-center gap-3 rounded-xl px-3 text-[14px] font-medium no-underline transition-colors duration-150";
const ITEM_ON = "bg-hover text-fg hover:text-fg";
const ITEM_OFF = "text-muted hover:bg-hover hover:text-fg";

/** More: Journal, Signal Lab, Settings and Sign out, in a native disclosure (works without script). With script it
 * also closes on a click outside, on Escape and when the page changes. In the dock it opens upwards. */
function MoreMenu({ path, email, dock = false }: { path: string; email: string; dock?: boolean }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.open = false;
  }, [path]);
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const d = ref.current;
      if (d?.open && !d.contains(e.target as Node)) d.open = false;
    };
    const onKey = (e: KeyboardEvent) => {
      const d = ref.current;
      if (e.key !== "Escape" || !d?.open) return;
      d.open = false;
      d.querySelector("summary")?.focus();
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);
  const on = inMore(path);
  return (
    <details ref={ref} className={cn("group relative", dock && "w-full")}>
      <summary
        className={cn(
          dock ? TAB : PILL,
          dock ? (on ? TAB_ON : TAB_OFF) : on ? PILL_ON : PILL_OFF,
          !dock && "gap-1.5",
          "list-none [&::-webkit-details-marker]:hidden",
        )}
      >
        {dock ? <Icon name="dots" className="size-5" strokeWidth={2.4} /> : null}
        More
        {dock ? null : <Icon name="chevron-down" className="transition-transform duration-200 group-open:rotate-180" />}
      </summary>
      <div className={cn("pop absolute right-0 z-40 flex w-56 flex-col rounded-2xl p-1.5", dock ? "bottom-full mb-3" : "top-full mt-2")}>
        {MORE.map((p) => {
          const cur = isCurrent(path, p.href);
          return (
            <Link key={p.href} href={p.href} aria-current={cur ? "page" : undefined} className={cn(ITEM, cur ? ITEM_ON : ITEM_OFF)}>
              <Icon name={p.icon} className="size-[18px]" />
              {p.label}
            </Link>
          );
        })}
        <div className="mx-2 my-1 h-px bg-line" />
        <form action="/auth/signout" method="post">
          <button type="submit" title={`Signed in as ${email}`} className={cn(ITEM, ITEM_OFF)}>
            <Icon name="logout" className="size-[18px]" />
            Sign out
          </button>
        </form>
      </div>
    </details>
  );
}

/** The desktop header's main navigation: This week, Candidates, Theses and More, as one segmented pill. Hidden on a
 * phone, where the dock takes its place. The current place is marked (aria-current). */
export function NavLinks({ email }: { email: string }) {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="Main" className={cn(SEG_TRACK, "hidden md:flex")}>
      {MAIN.map((p) => {
        const cur = isCurrent(path, p.href);
        return (
          <Link key={p.href} href={p.href} aria-current={cur ? "page" : undefined} className={cn(PILL, cur ? PILL_ON : PILL_OFF)}>
            {p.label}
          </Link>
        );
      })}
      <MoreMenu path={path} email={email} />
    </nav>
  );
}

/** The phone's bottom dock: the same four places as glass tabs with icons, floating over the page (hidden from md up,
 * where the header's pills take its place). */
export function Dock({ email }: { email: string }) {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="Main" className="fixed inset-x-4 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 md:hidden">
      <div className="glass mx-auto grid h-[68px] max-w-md grid-cols-4 items-center gap-1 rounded-full px-1.5">
        {MAIN.map((p) => {
          const cur = isCurrent(path, p.href);
          return (
            <Link key={p.href} href={p.href} aria-current={cur ? "page" : undefined} className={cn(TAB, cur ? TAB_ON : TAB_OFF)}>
              <Icon name={p.icon} className="size-5" />
              {p.label}
            </Link>
          );
        })}
        <MoreMenu path={path} email={email} dock />
      </div>
    </nav>
  );
}

/** The company search (overhaul PR 5): a plain GET form to /search, so it works without script; "/" jumps to it from
 * anywhere but a text field. app/(app)/search/page.tsx checks the query again on the server. */
export function SearchBox({ className }: { className?: string }) {
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
      if (typingIn(e.target as HTMLElement | null) || typingIn(document.activeElement as HTMLElement | null)) return;
      e.preventDefault();
      box.current?.focus();
      box.current?.select();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <form role="search" action="/search" method="get" className={cn("min-w-0", className)}>
      <label htmlFor="company-search" className="sr-only">
        Search companies
      </label>
      <div className="lift flex h-11 items-center gap-2 rounded-full pr-2 pl-3.5 focus-within:outline-2 focus-within:outline-accent md:h-10">
        <Icon name="search" className="text-subtle" />
        <input
          ref={box}
          id="company-search"
          name="q"
          type="search"
          maxLength={SEARCH_MAX}
          autoComplete="off"
          spellCheck={false}
          placeholder="Search a company"
          aria-keyshortcuts="/"
          className="h-full w-full min-w-0 bg-transparent text-[16px] text-fg placeholder:text-subtle focus-visible:outline-none md:text-[14px]"
        />
        <kbd aria-hidden="true" className="hidden shrink-0 rounded-md bg-hover px-1.5 py-0.5 text-[11px] font-medium text-subtle md:inline">
          /
        </kbd>
      </div>
    </form>
  );
}
