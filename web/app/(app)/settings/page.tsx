import { Empty, Flash, Page, Section } from "@/components/page";
import { SourceStatus } from "@/components/source-status";
import { SubmitButton } from "@/components/submit-button";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { configText } from "@/lib/config-files";
import { setting, sourceHealth, universeCounts, weightsVersions } from "@/lib/data";
import { env } from "@/lib/env";
import { one, type Query } from "@/lib/forms";
import { sourceLabel } from "@/lib/labels";
import { saveDiscipline } from "./actions";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "Settings" };

// BRIEF §6 Settings: universes, quotas, sources, allowed email; weights shown read-only (they change only through a
// PR). Plus the §11.9 discipline rule, which is configurable here.

function Yaml({ name, text }: { name: string; text: string | null }) {
  return text === null ? (
    <Empty>config/{name} isn&apos;t available in this deployment; see the repository.</Empty>
  ) : (
    <pre tabIndex={0} className="max-h-96 overflow-auto rounded-lg border border-gray-200 bg-gray-50 p-3 font-mono text-xs leading-relaxed text-gray-900">
      {text}
    </pre>
  );
}

export default async function Settings({ searchParams }: { searchParams: Promise<Query> }) {
  const { email } = await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
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
  const now = new Date();
  return (
    <Page title="Settings" description="Most settings live in the repository's config files and change through pull requests; they are shown here read-only.">
      <Flash error={one(q, "error")} ok={one(q, "ok")} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Section title="Sign-in" id="signin">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-700">Signed in as</dt>
            <dd className="font-medium break-all">{email}</dd>
            <dt className="text-gray-700">Allowed email</dt>
            <dd className="font-medium break-all">{env().APP_ALLOWED_EMAIL}</dd>
          </dl>
          <p className="mt-3 text-sm text-gray-700">Magic link only; change it in the deployment&apos;s APP_ALLOWED_EMAIL.</p>
        </Section>
        <Section title="Discipline" id="discipline" description="An earlier start-position entry needs a written override reason (§11.9).">
          <form action={saveDiscipline} className="flex flex-col gap-1.5">
            <Label htmlFor="weeks">Weeks a thesis must be old before a start-position entry</Label>
            <div className="flex items-center gap-2">
              <Input id="weeks" name="weeks" type="number" min="0" max="104" step="1" defaultValue={String(weeks)} className="w-28" required />
              <SubmitButton>Save</SubmitButton>
            </div>
          </form>
        </Section>
      </div>
      <Section title="Universes" id="universes">
        <Table label="Universe counts">
          <TableHeader>
            <TableRow>
              <TableHead>Market</TableHead>
              <TableHead num>In the universe</TableHead>
              <TableHead num>Tracked outside it</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(["us", "in"] as const).map((m) => (
              <TableRow key={m}>
                <TableCell className="font-medium">{m === "us" ? "US" : "India"}</TableCell>
                <TableCell num>{tally(m, true).toLocaleString("en-US")}</TableCell>
                <TableCell num>{tally(m, false).toLocaleString("en-US")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="mt-3 flex flex-col gap-2">
          <details>
            <summary className="text-sm font-medium">config/universe_us.yaml</summary>
            <div className="mt-2">
              <Yaml name="universe_us.yaml" text={universeUs} />
            </div>
          </details>
          <details>
            <summary className="text-sm font-medium">config/universe_in.yaml</summary>
            <div className="mt-2">
              <Yaml name="universe_in.yaml" text={universeIn} />
            </div>
          </details>
        </div>
      </Section>
      <Section title="LLM quotas" id="quotas" description="config/quotas.yaml: each provider's free-tier limits and the models in use.">
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
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s) => (
                <TableRow key={s.source}>
                  <TableCell className="font-medium">{sourceLabel(s.source)}</TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">
                    {s.last_success ? s.last_success.slice(0, 16).replace("T", " ") + "Z" : "never"}
                  </TableCell>
                  <TableCell>
                    <SourceStatus source={s} all={sources} now={now} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section
        title="Weights (read-only)"
        id="weights"
        description={
          <>
            Weights change only through a pull request with the <code>human-approved</code> label.
            {current ? ` In use: version ${current.version}, approved ${current.approved_at?.slice(0, 10) ?? ""}.` : " No approved version is recorded yet."}
          </>
        }
      >
        <Yaml name="weights.yaml" text={weightsFile} />
      </Section>
    </Page>
  );
}
