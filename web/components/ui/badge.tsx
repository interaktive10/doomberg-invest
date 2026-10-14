import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Badge: a colour's own text on its 15% tint (the tightest, down on a hovered row, is 4.8:1). No uppercase.
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
  {
    variants: {
      variant: {
        default: "bg-accent/15 text-accent ring-accent/30",
        secondary: "bg-raised text-muted ring-line-strong",
        destructive: "bg-down/15 text-down ring-down/35",
        warning: "bg-warn/15 text-warn ring-warn/35",
        success: "bg-up/15 text-up ring-up/35",
        outline: "bg-transparent text-muted ring-line-strong",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
