"use client";

import type { ReactNode } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { yScale } from "@/lib/chart";
import { INK, SERIES } from "@/lib/palette";
import { cn } from "@/lib/utils";

// Recharts line charts for the Company page (BRIEF §6), on the dark theme (lib/palette.ts mirrors globals.css: SVG
// attributes can't read CSS variables). The second and later series are dashed, so they differ without colour.
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

/** Charts on hairlines: each cell draws its top and left rule, and the frame hides the outer ones. */
export function ChartGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="overflow-hidden rounded-sm border border-line">
      <div className={cn("-mt-px -ml-px grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3", className)}>{children}</div>
    </div>
  );
}

export function LineChartCard({
  title,
  data,
  series,
  format,
  xKey = "period",
  className,
}: {
  title: string;
  data: Row[];
  series: Series[];
  format: Format;
  xKey?: string;
  className?: string;
}) {
  const points = data.filter((r) => series.some((s) => typeof r[s.key] === "number")).length;
  const y = yScale(data, series.map((s) => s.key));
  const first = series[0]?.key;
  const lastValue = first === undefined ? undefined : data.map((r) => r[first]).filter((v): v is number => typeof v === "number").at(-1);
  return (
    <figure className={cn("min-w-0 border-t border-l border-line bg-panel p-3", className)}>
      <figcaption className="mb-2 flex items-baseline justify-between gap-2 text-xs font-medium text-muted">
        <span>{title}</span>
        {lastValue !== undefined ? <span className="num text-fg">{fmt(lastValue, format)}</span> : null}
      </figcaption>
      {points > 0 ? (
        <div className="h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: INK.tick }} tickLine={false} axisLine={{ stroke: INK.axis }} minTickGap={24} />
              <YAxis
                tick={{ fontSize: 11, fill: INK.tick }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => fmt(v, format)}
                domain={y.domain}
                ticks={y.ticks}
                interval={0}
                width={52}
              />
              <Tooltip
                formatter={(v: unknown) => fmt(Number(v), format)}
                contentStyle={{ background: INK.tip, border: `1px solid ${INK.axis}`, borderRadius: 4, fontSize: 12, color: INK.fg }}
                labelStyle={{ color: INK.fg, fontWeight: 600 }}
                itemStyle={{ color: INK.fg }}
                cursor={{ stroke: INK.edge }}
              />
              {series.length > 1 ? <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} /> : null}
              {series.map((s, i) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={SERIES[i % SERIES.length]}
                  strokeWidth={1.5}
                  strokeDasharray={i > 0 ? "4 3" : undefined}
                  dot={points <= 3 ? { r: 2.5 } : false}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="py-8 text-center text-[13px] text-muted">No data yet.</p>
      )}
    </figure>
  );
}
