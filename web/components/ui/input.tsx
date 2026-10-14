import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Input, Textarea, Select (native), Label. Control borders are the edge colour (>= 3:1 on every surface).
const field =
  "rounded-sm border border-edge bg-field px-2.5 text-[13px] text-fg placeholder:text-subtle " +
  "focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent/40";

/** A radio or checkbox inside its label, read as a chip (thesis verdicts, post-mortem, screener filters); the box
 * stays visible for keyboard and screen-reader users. */
export const choiceChip =
  "flex cursor-pointer items-center gap-2 rounded-sm border border-edge bg-field px-2.5 py-1 text-[13px] text-fg has-checked:border-accent has-checked:bg-accent/10";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-8", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-20 w-full py-1.5", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(field, "h-8 pr-8", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-xs font-medium text-muted", className)} {...props} />;
}

/** A label above its control, with an optional hint under it. */
export function Field({ label, htmlFor, hint, children, className }: { label: React.ReactNode; htmlFor: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-subtle">{hint}</p> : null}
    </div>
  );
}
