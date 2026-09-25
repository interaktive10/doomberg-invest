import { Empty, Flash, Page, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { configText } from "@/lib/config-files";
import { setting, sourceHealth, universeCounts, weightsVersions } from "@/lib/data";
import { env } from "@/lib/env";
import { one, type Query } from "@/lib/forms";
import { saveDiscipline } from "./actions";

// BRIEF §6 Settings: universes, quotas, sources, allowed email; weights shown read-only (they change only through a
// PR). Plus the §11.9 discipline rule, which is configurable here.

function Yaml({ name, text }: { name: string; text: string | null }) {
  return text === null ? (
    <Empty>config/{name} isn&apos;t available in this deployment; see the repository.</Empty>
  ) : (
    <pre tabIndex={0} className="max-h-96 overflow-auto rounded-md border border-gray-300 bg-gray-50 p-3 text-xs">
      {text}
    </pre>
  );
}

export default async function Settings({ searchParams }: { searchParams: Promise<Query> }) {
  const q = await searchParams;
  const [counts, sources, versions, weeks, quotas, universeUs, universeIn, weightsFile] = await Promise.all([
    universeCounts(),
    sourceHealth(),
    weightsVersions(),
    setting<number | string>("position_min_thesis_weeks", 4),
    configText("quotas.yaml"),
    configText("universe_us.yaml"),
    configText("universe_in.yaml"),
    configText("weights.yaml"),
  ]);
  const tally = (m: string, inside: boolean) => counts.find((c) => c.market === m && c.in_universe === inside)?.count ?? 0;
  const current = versions.find((v) => v.approved_at !== null);
  return (
    <Page title="Settings">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <Section title="Sign-in" id="signin">
        <p className="text-sm">
          Allowed email: <strong>{env().APP_ALLOWED_EMAIL}</strong> (magic link only; change it in the deployment&apos;s APP_ALLOWED_EMAIL).
        </p>
      </Section>
      <Section title="Discipline" id="discipline">
        <form action={saveDiscipline} className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="weeks">Weeks a thesis must be old before a start-position entry</Label>
            <Input id="weeks" name="weeks" type="number" min="0" max="104" step="1" defaultValue={String(weeks)} className="w-28" required />
          </div>
          <Button type="submit">Save</Button>
        </form>
        <p className="mt-2 text-sm text-gray-700">An earlier entry needs a written override reason (§11.9).</p>
      </Section>
      <Section title="Universes" id="universes">
        <Table label="Universe counts">
          <TableHeader>
            <TableRow>
              <TableHead>Market</TableHead>
              <TableHead>In the universe</TableHead>
              <TableHead>Tracked outside it</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(["us", "in"] as const).map((m) => (
              <TableRow key={m}>
                <TableCell>{m === "us" ? "US" : "India"}</TableCell>
                <TableCell>{tally(m, true)}</TableCell>
                <TableCell>{tally(m, false)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium">config/universe_us.yaml</summary>
          <Yaml name="universe_us.yaml" text={universeUs} />
        </details>
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-medium">config/universe_in.yaml</summary>
          <Yaml name="universe_in.yaml" text={universeIn} />
        </details>
      </Section>
      <Section title="LLM quotas (config/quotas.yaml)" id="quotas">
        <Yaml name="quotas.yaml" text={quotas} />
      </Section>
      <Section title="Sources" id="sources">
        {sources.length === 0 ? (
          <Empty>No source has reported yet.</Empty>
        ) : (
          <Table label="Sources">
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Last success</TableHead>
                <TableHead>Stale</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s) => (
                <TableRow key={s.source}>
                  <TableCell>{s.source}</TableCell>
                  <TableCell>{s.last_success ? s.last_success.slice(0, 16).replace("T", " ") + "Z" : "never"}</TableCell>
                  <TableCell>{s.stale ? "yes" : "no"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section title="Weights (read-only)" id="weights">
        <p className="mb-2 text-sm text-gray-700">
          Weights change only through a pull request with the <code>human-approved</code> label.
          {current ? ` In use: version ${current.version}, approved ${current.approved_at?.slice(0, 10) ?? ""}.` : " No approved version is recorded yet."}
        </p>
        <Yaml name="weights.yaml" text={weightsFile} />
      </Section>
    </Page>
  );
}
