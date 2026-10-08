import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Badge. Text colours are the 800/900 shades on their 50 tints (axe contrast).
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
  {
    variants: {
      variant: {
        default: "bg-blue-50 text-blue-900 ring-blue-700/25",
        secondary: "bg-gray-100 text-gray-800 ring-gray-500/25",
        destructive: "bg-red-50 text-red-900 ring-red-700/25",
        warning: "bg-amber-50 text-amber-950 ring-amber-700/30",
        success: "bg-green-50 text-green-900 ring-green-700/25",
        outline: "bg-white text-gray-800 ring-gray-300",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
