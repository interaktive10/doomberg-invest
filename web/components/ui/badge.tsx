import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Badge as a soft chip: a colour's own text on its 10% tint (>= 4.5:1 in both themes, tests/palette.test.ts),
// or muted text on the chip grey. No uppercase.
export const badgeVariants = cva(
  "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12px] leading-none font-semibold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-accent/10 text-accent",
        secondary: "bg-hover text-muted",
        destructive: "bg-down/10 text-down",
        warning: "bg-warn/10 text-warn",
        success: "bg-up/10 text-up",
        outline: "bg-transparent text-muted ring-1 ring-inset ring-line-strong",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
