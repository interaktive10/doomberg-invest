import { tileText, tintFor, type Tint } from "@/lib/visual";
import { cn } from "@/lib/utils";

const TINT: Record<Tint, string> = { sky: "bg-tint-sky", sage: "bg-tint-sage", sand: "bg-tint-sand", clay: "bg-tint-clay" };

const SIZE = {
  sm: "size-10 rounded-[13px] text-[11px]",
  md: "size-11 rounded-[14px] text-[12px]",
  lg: "size-[72px] rounded-[22px] text-[16px]",
} as const;

/** A company's ticker on a soft tinted square (the same company always gets the same tint), the face of a row or a
 * card. Decorative: the name beside it is what a screen reader reads. */
export function TickerTile({ ticker, size = "md", tint, className }: { ticker: string; size?: keyof typeof SIZE; tint?: Tint; className?: string }) {
  const text = tileText(ticker);
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid shrink-0 place-items-center font-bold tracking-[-0.01em] text-fg",
        SIZE[size],
        TINT[tint ?? tintFor(ticker)],
        text.length >= 5 && "text-[10px]",
        className,
      )}
    >
      {text}
    </span>
  );
}
