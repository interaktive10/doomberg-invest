import { Badge } from "@/components/ui/badge";
import { FAMILY_LABEL, label } from "@/lib/labels";

/** Signal family ids as badges with their names (the Company page's score line). */
export function FamilyBadges({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((f) => (
        <Badge key={f} variant="secondary">
          {label(FAMILY_LABEL, f)}
        </Badge>
      ))}
    </span>
  );
}
