import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Input, Textarea, Select (native), Label, as Curator's soft wells: the field colour inside a hairline
// border that turns accent on focus. 44 px tall on a phone, 40 px from md up; 16 px text on a phone, so iOS doesn't
// zoom the page when a field takes focus.
const field =
  "rounded-xl border border-line-strong bg-field px-3.5 text-[16px] text-fg placeholder:text-subtle transition-colors duration-150 md:text-[14px] " +
  "focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent/30";

/** A radio or checkbox inside its label, read as a pill (thesis verdicts, post-mortem); the box stays visible for
 * keyboard and screen-reader users. */
export const choiceChip =
  "flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line-strong bg-field px-3.5 text-[14px] text-fg transition-colors duration-150 has-checked:border-accent has-checked:bg-accent/10 md:min-h-10";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-11 md:h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-24 w-full py-2.5", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(field, "h-11 pr-9 md:h-10", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-[13px] font-medium text-muted", className)} {...props} />;
}

/** A label above its control, with an optional hint under it. */
export function Field({ label, htmlFor, hint, children, className }: { label: React.ReactNode; htmlFor: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-[13px] text-subtle">{hint}</p> : null}
    </div>
  );
}
