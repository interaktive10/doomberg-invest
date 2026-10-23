import { Disclosure } from "@/components/disclosure";
import { Icon, type IconName } from "@/components/icons";
import type { KillCriterion } from "@/lib/data";
import { killNow, killRule } from "@/lib/explain";
import { killSentence } from "@/lib/labels";
import { cn } from "@/lib/utils";

const MARK: Record<KillCriterion["status"], { icon: IconName; dot: string; text: string }> = {
  ok: { icon: "check", dot: "bg-up/10 text-up", text: "text-muted" },
  triggered: { icon: "alert", dot: "bg-down/10 text-down", text: "text-down" },
  unknown: { icon: "minus", dot: "bg-hover text-subtle", text: "text-muted" },
};

/** "What would kill it": each kill criterion as a checklist line, its rule in a few words and where it stands ("Now
 * 24.0% · safe"), marked with a tick, an alert or a dash. `detail` adds a Why disclosure with the card's reason, the
 * full sentence and when it was checked (the Thesis page); the metric's id is the rule's title. */
export function KillList({ kills, detail = false, className }: { kills: readonly KillCriterion[]; detail?: boolean; className?: string }) {
  return (
    <ul aria-label="Kill criteria" className={cn("flex flex-col gap-3.5", className)}>
      {kills.map((k) => {
        const m = MARK[k.status] ?? MARK.unknown;
        return (
          <li key={k.id} className="flex items-start gap-3">
            <span aria-hidden="true" className={cn("mt-px grid size-6 shrink-0 place-items-center rounded-full", m.dot)}>
              <Icon name={m.icon} className="size-3.5" strokeWidth={3} />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[14px] font-semibold text-fg" title={k.metric}>
                {killRule(k)}
              </span>
              <span className={cn("num text-[13px]", m.text)}>{killNow(k)}</span>
              {detail ? (
                <Disclosure summary="Why">
                  <div className="flex flex-col gap-1 text-[13px]">
                    {k.why ? <p className="text-fg">{k.why}</p> : null}
                    <p>{killSentence(k)}</p>
                    <p className="num">
                      <code>{k.metric}</code>
                      {k.last_checked ? ` · checked week ${k.last_checked}` : ""}
                      {k.triggered_week ? ` · triggered week ${k.triggered_week}` : ""}
                    </p>
                  </div>
                </Disclosure>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
