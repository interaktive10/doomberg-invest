"use client";

import type { ReactNode } from "react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { yScale } from "@/lib/chart";
import { INK, SERIES } from "@/lib/palette";
import { cn } from "@/lib/utils";

// Recharts charts for the Company page (BRIEF §6) in the sparkline style: the number it ends on, then a soft area under
// a line over a zero baseline, no axes or grid; a tooltip gives each quarter's value. Colours are CSS variables
// (lib/palette.ts), so a chart follows the theme with no re-render. The second and later series are dashed lines
// without an area, so they differ without colour.
export type Format = "big" | "pct" | "x" | "num";
export interface Series {
  key: string;
  label: string;
}
export type Row = Record<string, string | number | null>;

export function fmt(v: number, format: Format): string {
  if (!Number.isFinite(v)) return "";
  switch (format) {
    case "pct":
      return `${(v * 100).toFixed(0)}%`;
    case "x":
      return `${v.toFixed(1)}x`;
    case "num":
      return v.toFixed(0);
    case "big": {
      const a = Math.abs(v);
      const [d, s] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
      return `${(v / d).toFixed(1)}${s}`;
    }
  }
}

/** Chart cards side by side: one column on a phone, two from sm, three from xl. */
export function ChartGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3", className)}>{children}</div>;
}

/** One chart: its title and period range, the value it ends on, the chart, and a one-line `note` under it. A tile
 * inside a sheet by default; `surface="sheet"` makes it a sheet of its own (a grid on the canvas). */
export function LineChartCard({
  title,
  data,
  series,
  format,
  xKey = "period",
  note,
  surface = "tile",
  className,
}: {
  title: string;
  data: Row[];
  series: Series[];
  format: Format;
  xKey?: string;
  note?: ReactNode;
  surface?: "tile" | "sheet";
  className?: string;
}) {
  const rows = data.filter((r) => series.some((s) => typeof r[s.key] === "number"));
  const y = yScale(data, series.map((s) => s.key));
  const first = series[0]?.key;
  const lastValue = first === undefined ? undefined : data.map((r) => r[first]).filter((v): v is number => typeof v === "number").at(-1);
  const from = rows[0]?.[xKey];
  const to = rows.at(-1)?.[xKey];
  return (
    <figure className={cn("flex min-w-0 flex-col gap-2", surface === "sheet" ? "sheet p-5" : "tile p-4", className)}>
      <figcaption className="flex flex-col gap-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-[14px] font-semibold text-fg">{title}</span>
          {from !== undefined && from !== null && rows.length > 1 ? (
            <span className="num shrink-0 text-[12px] text-subtle">
              {String(from)} – {String(to)}
            </span>
          ) : null}
        </span>
        {lastValue !== undefined ? <span className="num text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">{fmt(lastValue, format)}</span> : null}
      </figcaption>
      {rows.length > 0 ? (
        <div className="h-20 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
              <XAxis dataKey={xKey} hide />
              <YAxis hide domain={y.domain} />
              <ReferenceLine y={0} stroke={INK.axis} strokeWidth={1} />
              <Tooltip
                formatter={(v: unknown) => fmt(Number(v), format)}
                contentStyle={{
                  background: INK.tip,
                  border: "none",
                  borderRadius: 12,
                  boxShadow: "var(--pop-shadow)",
                  fontSize: 12,
                  color: INK.fg,
                }}
                labelStyle={{ color: INK.muted, fontWeight: 600 }}
                itemStyle={{ color: INK.fg }}
                cursor={{ stroke: INK.axis }}
              />
              {series.map((s, i) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={SERIES[i % SERIES.length]}
                  strokeWidth={i === 0 ? 2.5 : 1.75}
                  strokeDasharray={i > 0 ? "4 3" : undefined}
                  fill={i === 0 ? SERIES[0] : "none"}
                  fillOpacity={i === 0 ? 0.14 : 0}
                  baseValue={0}
                  connectNulls={false}
                  dot={rows.length <= 3 ? { r: 3, fill: SERIES[i % SERIES.length], stroke: INK.panel, strokeWidth: 1 } : false}
                  activeDot={{ r: 3.5, stroke: INK.panel, strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="py-6 text-center text-[13px] text-muted">No data yet.</p>
      )}
      {series.length > 1 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
          {series.map((s, i) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <svg aria-hidden="true" width="16" height="4" viewBox="0 0 16 4">
                <line x1="1" x2="15" y1="2" y2="2" stroke={SERIES[i % SERIES.length]} strokeWidth="2" strokeLinecap="round" strokeDasharray={i > 0 ? "3 3" : undefined} />
              </svg>
              {s.label}
            </li>
          ))}
        </ul>
      ) : null}
      {note ? <p className="text-[13px] text-muted">{note}</p> : null}
    </figure>
  );
}
