"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** A native disclosure used as a menu or a popover closes on a press outside it and on Escape (focus goes back to its
 * summary). Without script it still opens and closes on its summary. A pointerdown, not a click: iOS Safari sends no
 * click to the document for a tap on plain content (PR 6 final review C10). */
export function useCloseOnOutside(ref: { current: HTMLDetailsElement | null }): void {
  useEffect(() => {
    const onDown = (e: PointerEvent) => {
      const d = ref.current;
      if (d?.open && !d.contains(e.target as Node)) d.open = false;
    };
    const onKey = (e: KeyboardEvent) => {
      const d = ref.current;
      if (e.key !== "Escape" || !d?.open) return;
      d.open = false;
      d.querySelector("summary")?.focus();
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref]);
}

/** A <details> popover (Candidates' Dismiss and Filters) that closes like the More menu: on a press outside or on
 * Escape. Its summary and body are the caller's, rendered on the server. */
export function DetailsMenu({ className, children }: { className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useCloseOnOutside(ref);
  return (
    <details ref={ref} className={className}>
      {children}
    </details>
  );
}
