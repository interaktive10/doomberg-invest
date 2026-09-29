import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Badge.
export const badgeVariants = cva("inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      default: "border-blue-800 bg-blue-50 text-blue-900",
      secondary: "border-gray-400 bg-gray-50 text-gray-900",
      destructive: "border-red-800 bg-red-50 text-red-900",
      warning: "border-amber-700 bg-amber-50 text-gray-900",
      success: "border-green-800 bg-green-50 text-green-900",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
