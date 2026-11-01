"use client";

import { useRouter } from "next/navigation";

export interface PickerGroup {
  label: string;
  options: { value: string; label: string }[];
}

/** The Themes screen's dropdown: every theme by category (and the retired ones), opening the one picked. A plain GET
 * form underneath, so it works without script (the button submits it). */
export function ThemePicker({ groups, current }: { groups: PickerGroup[]; current: string }) {
  const router = useRouter();
  return (
    <form method="get" action="/themes" className="flex min-w-0 items-center gap-2">
      <label htmlFor="theme-pick" className="sr-only">
        Pick a theme
      </label>
      <select
        id="theme-pick"
        name="t"
        defaultValue={current}
        onChange={(e) => router.push(e.target.value ? `/themes?t=${encodeURIComponent(e.target.value)}` : "/themes")}
        className="lift outline-edge h-11 max-w-full min-w-0 rounded-full bg-field px-4 text-[15px] text-fg md:h-10 md:w-80"
      >
        <option value="">All themes</option>
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <noscript>
        <button type="submit" className="h-10 rounded-full bg-ink px-4 text-[14px] font-semibold text-on-ink">
          Show
        </button>
      </noscript>
    </form>
  );
}
