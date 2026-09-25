import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Table. The wrapper scrolls sideways on a phone (390 px) instead of the page; it is focusable so a
// keyboard can scroll it too (axe scrollable-region-focusable), and a named region when `label` is given.
export function Table({ className, label, ...props }: ComponentProps<"table"> & { label?: string }) {
  return (
    <div className="w-full overflow-x-auto" tabIndex={0} {...(label ? { role: "region", "aria-label": label } : {})}>
      <table className={cn("w-full caption-bottom border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader(props: ComponentProps<"thead">) {
  return <thead {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("border-b border-gray-200", className)} {...props} />;
}

export function TableHead({ className, ...props }: ComponentProps<"th">) {
  return <th scope="col" className={cn("px-2 py-1.5 text-left font-semibold whitespace-nowrap", className)} {...props} />;
}

export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("px-2 py-1.5 align-top", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("mt-2 text-left text-xs text-gray-700", className)} {...props} />;
}
