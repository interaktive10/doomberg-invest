import type { ReactNode } from "react";
import { TONE_WORD, type Tone } from "@/lib/palette";
import { cn } from "@/lib/utils";
import { kindsLabel } from "@/lib/visual";

// Background classes per tone, spelled out so Tailwind sees them.
const DOT: Record<Tone, string> = {
  business: "bg-fam-business",
  insiders: "bg-fam-insiders",
  ownership: "bg-fam-ownership",
  text: "bg-fam-text",
  evidence: "bg-accent",
  gap: "bg-gap",
  up: "bg-up",
  down: "bg-down",
  warn: "bg-warn",
  muted: "bg-subtle",
};

/** A small coloured dot: an evidence family (business, insiders, ownership, text), a score or a meaning. Decorative; the
 * words beside it carry the meaning. */
export function Dot({ tone, className }: { tone: Tone; className?: string }) {
  return <span aria-hidden="true" className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], className)} />;
}

/** A chip's ground: the soft grey (plain), or a meaning's own 10% tint with its colour as the text (>= 4.5:1 in both
 * themes, tests/palette.test.ts): "Data as of Oct 17" in warn, "No red flags" in good. */
const VARIANT = {
  plain: "bg-hover text-fg",
  accent: "bg-accent/10 text-accent",
  good: "bg-up/10 text-up",
  warn: "bg-warn/10 text-warn",
  bad: "bg-down/10 text-down",
} as const;

export type ChipVariant = keyof typeof VARIANT;

/** md: a fact on its own ("Insiders bought $1.8M"); sm: a tag beside a name or a figure, the size of a Badge ("Lab:
 * unproven", "On time", "+4.2%"). */
const SIZE = {
  md: "min-h-8 gap-2 px-3 py-1 text-[13px]",
  sm: "min-h-6 gap-1.5 px-2.5 py-0.5 text-[12px]",
} as const;

/** A soft pill with one short fact ("Insiders bought $1.8M"), led by a family dot when `dot` is given. `title` can hold
 * the code or the detail (S7, the filing) so the chip itself stays in plain words. */
export function Chip({
  children,
  dot,
  variant = "plain",
  size = "md",
  title,
  className,
}: {
  children: ReactNode;
  dot?: Tone;
  variant?: ChipVariant;
  size?: keyof typeof SIZE;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded-full",
        SIZE[size],
        VARIANT[variant],
        variant !== "plain" && "font-medium",
        className,
      )}
    >
      {dot ? <Dot tone={dot} /> : null}
      {children}
    </span>
  );
}

/** One dot per kind of evidence that agrees (business, insiders, ...): a small reward that fills as kinds add up. Read
 * as one image: "2 kinds of evidence: business, insiders". `of` draws that many slots, the empty ones as rings. */
export function DotRow({ tones, of, className }: { tones: readonly Tone[]; of?: number; className?: string }) {
  const said = kindsLabel(tones.map((t) => TONE_WORD[t] ?? t));
  const empty = Math.max(0, (of ?? tones.length) - tones.length);
  return (
    <span role="img" aria-label={said} title={said} className={cn("inline-flex items-center gap-1", className)}>
      {tones.map((t, i) => (
        <Dot key={i} tone={t} className="size-2.5" />
      ))}
      {Array.from({ length: empty }, (_, i) => (
        <span key={`e${i}`} aria-hidden="true" className="inline-block size-2.5 shrink-0 rounded-full ring-1 ring-edge ring-inset" />
      ))}
    </span>
  );
}

/** A legend: one dot and word per tone ("business", "insiders"), for a group of chips or a split bar. Each label is
 * one run of text, so a long one wraps under its own start with the dot on its first line (PR 6 final review HC-9). */
export function Legend({ items, className }: { items: readonly { tone: Tone; label: ReactNode }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-muted", className)}>
      {items.map((it, i) => (
        <li key={i} className="inline-flex items-baseline gap-1.5">
          <Dot tone={it.tone} className="-translate-y-px" />
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  );
}
