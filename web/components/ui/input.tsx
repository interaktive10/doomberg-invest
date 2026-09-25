import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Input, Textarea, Select (native), Label.
const field =
  "rounded-md border border-gray-500 bg-white px-2 py-1.5 text-sm text-gray-900 focus-visible:outline-2 " +
  "focus-visible:outline-offset-1 focus-visible:outline-blue-800";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-20 w-full", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(field, "h-9", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium", className)} {...props} />;
}
