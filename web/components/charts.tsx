"use client";

import type { ReactNode } from "react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartValue, yScale, type ChartFormat } from "@/lib/chart";
import { quarterLabel } from "@/lib/dates";
import { CHART_TONE, INK, SERIES, type ChartTone } from "@/lib/palette";
import { cn } from "@/lib/utils";

// Recharts charts for the Company page (BRIEF §6) in the sparkline style: the number it ends on, then a soft area under
// a line over a zero baseline, no axes or grid; a tooltip gives each quarter's value. Colours are CSS variables
// (lib/palette.ts), so a chart follows the theme with no re-render; each card has its own colour (`tone`, the Company
// mock's accent, business green and insiders blue). The second and later series are dashed lines without an area, so
// they differ without colour. Figures read as the page says them (lib/chart.ts chartValue: "$818M", "3.9×", "5.3%"),
// periods as quarters ("Q3 ’23 – Q2 ’26"). The drawing itself is hidden from screen readers: the caption and the note
// under it say what it shows.
export type Format = ChartFormat;
export interface Series {
  key: string;
  label: string;
}
export type Row = Record<string, string | number | null>;

/** Chart cards side by side: one column on a phone, two from sm, three from xl. */
export function ChartGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3", className)}>{children}</div>;
}

/** One chart: its title and period range, the value it ends on, the chart, and a one-line `note` under it. A tile
 * inside a sheet by default; `surface="sheet"` makes it a sheet of its own (a grid on the canvas). `currency` is the
 * page's, for a "money" chart. */
export function LineChartCard({
  title,
  data,
  series,
  format,
  currency,
  tone = "accent",
  xKey = "period",
  note,
  surface = "tile",
  className,
}: {
  title: string;
  data: Row[];
  series: Series[];
  format: Format;
  currency?: string;
  tone?: ChartTone;
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
  const colour = (i: number) => (i === 0 ? CHART_TONE[tone] : SERIES[i % SERIES.length]);
  const value = (v: unknown) => chartValue(Number(v), format, currency);
  const period = (v: unknown) => quarterLabel(String(v ?? ""));
  return (
    <figure className={cn("flex min-w-0 flex-col gap-2", surface === "sheet" ? "sheet p-5" : "tile p-4", className)}>
      <figcaption className="flex flex-col gap-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-[14px] font-semibold text-fg">{title}</span>
          {from !== undefined && from !== null && rows.length > 1 ? (
            <span className="num shrink-0 text-[12px] text-subtle">
              {period(from)} – {period(to)}
            </span>
          ) : null}
        </span>
        {lastValue !== undefined ? <span className="num text-[24px] leading-tight font-bold tracking-[-0.02em] text-fg">{value(lastValue)}</span> : null}
      </figcaption>
      {rows.length > 0 ? (
        <div aria-hidden="true" className="h-20 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
              <XAxis dataKey={xKey} hide />
              <YAxis hide domain={y.domain} />
              <ReferenceLine y={0} stroke={INK.axis} strokeWidth={1} />
              <Tooltip
                formatter={value}
                labelFormatter={period}
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
                  stroke={colour(i)}
                  strokeWidth={i === 0 ? 2.5 : 1.75}
                  strokeDasharray={i > 0 ? "4 3" : undefined}
                  fill={i === 0 ? colour(0) : "none"}
                  fillOpacity={i === 0 ? 0.14 : 0}
                  baseValue={0}
                  connectNulls={false}
                  dot={rows.length <= 3 ? { r: 3, fill: colour(i), stroke: INK.panel, strokeWidth: 1 } : false}
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
                <line x1="1" x2="15" y1="2" y2="2" stroke={colour(i)} strokeWidth="2" strokeLinecap="round" strokeDasharray={i > 0 ? "3 3" : undefined} />
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
