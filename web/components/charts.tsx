"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
  const has = data.some((r) => series.some((s) => typeof r[s.key] === "number"));
  return (
    <figure className="rounded-lg border border-gray-300 p-3">
      <figcaption className="mb-2 text-sm font-semibold">{title}</figcaption>
      {has ? (
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 12, bottom: 5, left: 0 }}>
              <CartesianGrid stroke="#e5e7eb" />
              <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "#374151" }} minTickGap={24} />
              <YAxis tick={{ fontSize: 11, fill: "#374151" }} tickFormatter={(v: number) => fmt(v, format)} width={52} />
              <Tooltip formatter={(v: unknown) => fmt(Number(v), format)} />
              {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
              {series.map((s, i) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-sm text-gray-700">No data.</p>
      )}
    </figure>
  );
}
