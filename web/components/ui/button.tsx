import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Button (BRIEF §2.2) as Curator's pills: the primary one is ink (near-black in light, ivory in dark), the
// secondary a soft grey, the accent one blue, the outline one an edge-coloured ring (>= 3:1). Every size is 44 px tall
// on a phone (a thumb's target), smaller only from md up. Sizes are text-[14px]/text-[13px] (tailwind-merge reads both
// as font sizes).
export const buttonVariants = cva(
  "press inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium no-underline " +
    "transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-ink text-on-ink hover:bg-ink/85 hover:text-on-ink",
        accent: "bg-accent text-on-accent hover:bg-accent-hover hover:text-on-accent",
        destructive: "bg-down/10 text-down hover:bg-down/15 hover:text-down",
        outline: "bg-panel text-fg ring-1 ring-inset ring-edge hover:bg-hover hover:text-fg",
        secondary: "bg-hover text-fg hover:bg-track hover:text-fg",
        ghost: "text-muted hover:bg-hover hover:text-fg",
      },
      size: {
        default: "h-11 px-4 text-[14px] md:h-10",
        sm: "h-11 px-3.5 text-[13px] md:h-9",
        xs: "h-11 px-3 text-[13px] md:h-8",
        lg: "h-12 px-5 text-[15px] md:h-11",
        icon: "size-11 text-[14px] md:size-10",
      },
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
