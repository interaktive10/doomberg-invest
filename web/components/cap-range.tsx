"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useState, useTransition } from "react";
import { capText, clampRange, rangeParam, rangeText, type CapRange, type Market } from "@/lib/caps";
import { cn } from "@/lib/utils";

// The market-cap range (2026-11-02): two native sliders, From and To, over a list's steps (works with keyboard and
// screen readers as is). To's last position is "no maximum". Every stock list uses it: Winners filters its own report
// in the browser (CapRangeControl); Undervalued and Themes filter on the server from ?cap= (CapRangeLink).

export function CapRangeControl({
  market,
  steps,
  value,
  onChange,
  note,
  className,
}: {
  market: Market;
  steps: readonly number[];
  value: CapRange;
  onChange: (r: CapRange) => void;
  note?: string;
  className?: string;
}) {
  const id = useId();
  const n = steps.length;
  const r = clampRange(value, n);
  const toText = (hi: number) => (hi >= n ? "No maximum" : capText(market, steps[hi]!));
  if (n < 2) return null;
  return (
    <fieldset className={cn("flex w-full max-w-md min-w-0 flex-col gap-2 sm:w-auto sm:min-w-[20rem]", className)}>
      <legend className="flex w-full items-baseline justify-between gap-3 text-[14px] text-muted">
        <span>Market cap</span>
        <span className="num text-[16px] font-bold text-fg">{rangeText(market, steps, r)}</span>
      </legend>
      <div className="grid grid-cols-[3rem_1fr] items-center gap-x-3 gap-y-1.5 text-[13px] text-muted">
        <label htmlFor={`${id}-lo`}>From</label>
        <input
          id={`${id}-lo`}
          type="range"
          min={0}
          max={n - 1}
          step={1}
          value={r.lo}
          onChange={(e) => {
            const lo = Number(e.target.value);
            onChange(clampRange({ lo, hi: Math.max(r.hi, lo + 1) }, n));
          }}
          aria-valuetext={capText(market, steps[r.lo]!)}
          className="w-full accent-accent"
        />
        <label htmlFor={`${id}-hi`}>To</label>
        <input
          id={`${id}-hi`}
          type="range"
          min={1}
          max={n}
          step={1}
          value={r.hi}
          onChange={(e) => {
            const hi = Number(e.target.value);
            onChange(clampRange({ lo: Math.min(r.lo, hi - 1), hi }, n));
          }}
          aria-valuetext={toText(r.hi)}
          className="w-full accent-accent"
        />
      </div>
      <div aria-hidden="true" className="flex justify-between pl-[3.75rem] text-[11px] text-subtle">
        <span>{capText(market, steps[0]!)}</span>
        <span>No maximum</span>
      </div>
      {note ? <p className="text-[12px] text-subtle">{note}</p> : null}
    </fieldset>
  );
}

/** The range kept in the address (?cap=lo-hi, or ?<param>=), so a server-rendered list filters on it and a link keeps
 * it; the page re-renders when it changes. */
export function CapRangeLink({
  market,
  steps,
  value,
  param = "cap",
  note,
  className,
}: {
  market: Market;
  steps: readonly number[];
  value: CapRange;
  param?: string;
  note?: string;
  className?: string;
}) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const [shown, setShown] = useState(value);
  const [pending, start] = useTransition();
  // the address changed from elsewhere (Clear filters, back): show its range
  useEffect(() => setShown(value), [value.lo, value.hi]);
  return (
    <div aria-busy={pending} className={cn("transition-opacity", pending && "opacity-70", className)}>
      <CapRangeControl
        market={market}
        steps={steps}
        value={shown}
        note={note}
        onChange={(r) => {
          setShown(r);
          const q = new URLSearchParams(params.toString());
          const v = rangeParam(r, steps.length);
          if (v) q.set(param, v);
          else q.delete(param);
          const s = q.toString();
          start(() => router.replace(s ? `${path}?${s}` : path, { scroll: false }));
        }}
      />
    </div>
  );
}
