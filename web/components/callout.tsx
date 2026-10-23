import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons";
import { cn } from "@/lib/utils";

export type CalloutTone = "info" | "warn" | "good" | "bad";

const TONE: Record<CalloutTone, { box: string; icon: string; name: IconName }> = {
  info: { box: "bg-hover text-muted", icon: "text-accent", name: "info" },
  warn: { box: "bg-warn/10 text-fg", icon: "text-warn", name: "alert" },
  good: { box: "bg-up/10 text-fg", icon: "text-up", name: "check" },
  bad: { box: "bg-down/10 text-fg", icon: "text-down", name: "alert" },
};

/** One line that needs saying, in a soft tile with an icon: a hint (info), a heads-up (warn), all clear (good) or a
 * problem (bad). `role` makes it the page's status or alert (Flash). */
export function Callout({
  tone = "info",
  children,
  role,
  className,
}: {
  tone?: CalloutTone;
  children: ReactNode;
  role?: "status" | "alert";
  className?: string;
}) {
  const t = TONE[tone];
  return (
    <div role={role} className={cn("flex items-start gap-3 rounded-tile px-4 py-3 text-[14px]", t.box, className)}>
      <Icon name={t.name} className={cn("mt-0.5 size-[18px]", t.icon)} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
