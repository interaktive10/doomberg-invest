import { TONE_VAR, type Tone } from "@/lib/palette";
import { sparkGeometry } from "@/lib/visual";
import { cn } from "@/lib/utils";

const W = 300;
const H = 80;

/** A series as a soft area under a line over a zero baseline, with no axes (the number it ends on sits above it, in the
 * page). Pure SVG, so it renders on the server; it stretches to its box's width. A null in `values` breaks the line;
 * a stretch of one value is a dot. `label` names the image ("Revenue, 12 quarters"). */
export function Sparkline({
  values,
  label,
  kind = "evidence",
  height = 64,
  className,
}: {
  values: readonly (number | null | undefined)[];
  label: string;
  kind?: Tone;
  height?: number;
  className?: string;
}) {
  const g = sparkGeometry(values, W, H);
  const color = TONE_VAR[kind];
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      width="100%"
      height={height}
      className={cn("block overflow-visible", className)}
    >
      <line x1="0" x2={W} y1={g.zero} y2={g.zero} strokeWidth="1" vectorEffect="non-scaling-stroke" className="stroke-line-strong" />
      {g.runs.map((r, i) => (
        <g key={i}>
          <polygon points={r.area} fill={color} fillOpacity="0.14" />
          <polyline
            points={r.line}
            fill="none"
            stroke={color}
            strokeWidth={r.dot ? 6 : 2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </g>
      ))}
    </svg>
  );
}
