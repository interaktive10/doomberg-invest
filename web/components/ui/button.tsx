import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Button (BRIEF §2.2) in the dark terminal look: on-accent on accent (9.5:1), fg on raised (15:1), down on
// its own tint for the destructive one. Sizes are text-[13px]/text-xs (tailwind-merge reads both as font sizes).
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-sm text-[13px] font-medium no-underline " +
    "transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-accent text-on-accent hover:bg-accent-hover hover:text-on-accent",
        destructive: "bg-down/15 text-down ring-1 ring-inset ring-down/50 hover:bg-down/20 hover:text-down",
        outline: "border border-edge bg-raised text-fg hover:bg-hover hover:text-fg",
        secondary: "bg-raised text-fg ring-1 ring-inset ring-line-strong hover:bg-hover hover:text-fg",
        ghost: "text-muted hover:bg-raised hover:text-fg",
      },
      size: { default: "h-8 px-3", sm: "h-7 px-2.5 text-xs", xs: "h-7 px-2 text-xs", lg: "h-10 px-5 text-sm" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
