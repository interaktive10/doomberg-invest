import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Button (BRIEF §2.2), with colours that keep axe's contrast rule (white on blue-800, gray-900 on white).
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium no-underline " +
    "transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-800 " +
    "disabled:pointer-events-none disabled:opacity-60",
  {
    variants: {
      variant: {
        default: "bg-blue-800 text-white hover:bg-blue-900",
        destructive: "bg-red-800 text-white hover:bg-red-900",
        outline: "border border-gray-500 bg-white text-gray-900 hover:bg-gray-100",
        ghost: "text-gray-900 hover:bg-gray-100",
      },
      size: { default: "h-9 px-3 py-1.5", sm: "h-8 px-2.5 text-xs", lg: "h-10 px-5" },
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
