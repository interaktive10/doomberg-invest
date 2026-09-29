"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { yDomain } from "@/lib/chart";

// Recharts line charts for the Company page (BRIEF §6). Dark series colours keep the legend text readable (axe).
export type Format = "big" | "pct" | "x" | "num";
export interface Series {
  key: string;
  label: string;
}
export type Row = Record<string, string | number | null>;

const COLORS = ["#1e40af", "#166534", "#991b1b", "#92400e"] as const;

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

export function LineChartCard({
  title,
  data,
  series,
  format,
  xKey = "period",
}: {
  title: string;
  data: Row[];
  series: Series[];
  format: Format;
  xKey?: string;
}) {
  const points = data.filter((r) => series.some((s) => typeof r[s.key] === "number")).length;
  return (
    <figure className="rounded-lg border border-gray-200 bg-white p-3">
      <figcaption className="mb-2 text-sm font-semibold text-gray-900">{title}</figcaption>
      {points > 0 ? (
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#eef0f3" vertical={false} />
              <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "#374151" }} tickLine={false} axisLine={{ stroke: "#d1d5db" }} minTickGap={24} />
              <YAxis
                tick={{ fontSize: 11, fill: "#374151" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => fmt(v, format)}
                domain={yDomain(data, series.map((s) => s.key))}
                width={52}
              />
              <Tooltip
                formatter={(v: unknown) => fmt(Number(v), format)}
                contentStyle={{ borderRadius: 8, borderColor: "#e5e7eb", fontSize: 12 }}
                labelStyle={{ color: "#111827", fontWeight: 600 }}
              />
              {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
              {series.map((s, i) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={points <= 3 ? { r: 3 } : false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-gray-700">No data yet.</p>
      )}
    </figure>
  );
}
