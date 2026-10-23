"use client";

import { useEffect } from "react";
import { hashId } from "@/lib/nav";

/** Opens the closed disclosures around the element the address's #hash names, then scrolls to it: a card's fact
 * citation (/company/<id>#fact-<id>) lands inside the Company page's folded quotes, and not every browser opens a
 * <details> for a fragment. Renders nothing; without script the quotes are one tap away. */
export function OpenTarget() {
  useEffect(() => {
    const open = () => {
      const id = hashId(window.location.hash); // "" for a malformed one, so a garbled link still opens the page
      const el = id ? document.getElementById(id) : null;
      if (el === null) return;
      let opened = false;
      for (let d = el.parentElement?.closest("details") ?? null; d !== null; d = d.parentElement?.closest("details") ?? null) {
        if (!d.open) {
          d.open = true;
          opened = true;
        }
      }
      if (opened) el.scrollIntoView({ block: "start" });
    };
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, []);
  return null;
}
