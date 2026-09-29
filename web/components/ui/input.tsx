import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Input, Textarea, Select (native), Label.
const field =
  "rounded-md border border-gray-400 bg-white px-2.5 py-1.5 text-sm text-gray-900 shadow-sm placeholder:text-gray-600 " +
  "focus-visible:border-blue-700 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-blue-700/30";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-20 w-full", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(field, "h-9 pr-8", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium text-gray-900", className)} {...props} />;
}

/** A label above its control, with an optional hint under it. */
export function Field({ label, htmlFor, hint, children, className }: { label: React.ReactNode; htmlFor: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-gray-700">{hint}</p> : null}
    </div>
  );
}
