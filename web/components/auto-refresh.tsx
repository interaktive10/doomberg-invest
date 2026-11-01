"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-reads the screen every `seconds` while the tab is visible (a research entry whose card is being written:
 * research.yml runs every 10 minutes). Nothing to read or click. */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
