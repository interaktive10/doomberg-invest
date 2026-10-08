import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Card.
export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-2xl border border-gray-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04)]", className)} {...props} />;
}

export function CardTitle({ className, ...props }: ComponentProps<"h3">) {
  return <h3 className={cn("font-semibold leading-tight", className)} {...props} />;
}

export function CardContent({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mt-2 text-sm", className)} {...props} />;
}
