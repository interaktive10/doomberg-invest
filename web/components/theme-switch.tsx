"use client";

import { useState } from "react";
import { Icon } from "@/components/icons";
import { DARK, LIGHT } from "@/lib/palette";
import { nextTheme, resolvedTheme, THEME_NAME, themeCookie, themeLabel, type ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/utils";

const ICON = { auto: "auto", light: "sun", dark: "moon" } as const;

/** The header's theme button: each press moves Auto -> Light -> Dark -> Auto. It stores the choice in the theme cookie
 * (the server reads it for the next page, lib/theme-server.ts) and sets data-theme on <html> now, so the page changes
 * at once without a reload. Its name says the mode it is in. */
export function ThemeSwitch({ initial, className }: { initial: ThemeMode; className?: string }) {
  const [mode, setMode] = useState<ThemeMode>(initial);
  const next = nextTheme(mode);
  const choose = () => {
    document.cookie = themeCookie(next);
    const root = document.documentElement;
    if (next === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
    // the phone's status bar follows the page (app/layout.tsx sets it on the server for the next load); under Auto a
    // tag the server wrote for one scheme (its media query) keeps that scheme's colour
    const deviceDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
      const media = meta.getAttribute("media") ?? "";
      const dark = next === "auto" && media !== "" ? media.includes("dark") : resolvedTheme(next, deviceDark) === "dark";
      meta.content = dark ? DARK.canvas : LIGHT.canvas;
    }
    setMode(next);
  };
  return (
    <button
      type="button"
      onClick={choose}
      aria-label={themeLabel(mode)}
      title={`${themeLabel(mode)}. Press for ${THEME_NAME[next]}.`}
      className={cn("lift press grid size-11 shrink-0 place-items-center rounded-full text-fg md:size-10", className)}
    >
      <Icon name={ICON[mode]} className="size-[18px]" />
    </button>
  );
}
