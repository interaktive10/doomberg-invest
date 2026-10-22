import { Markdown } from "@/components/markdown";
import { Empty, Kpi, KpiRibbon, Page, Section } from "@/components/page";
import { StaleBanner } from "@/components/stale";
import { requireUser } from "@/lib/auth";
import { stripSection } from "@/lib/cards";
import { latestDigest, overview, sourceHealth } from "@/lib/data";

export const metadata = { title: "This week" };

// BRIEF §6 Home, simplified (Manzoor, 2026-10-08): what needs a look this week and the weekly digest. Source health
// and LLM quota use moved to Settings; the stale-data banner shows here only (overhaul PR 4) when a US source is late.
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, o, sources] = await Promise.all([latestDigest(), overview(), sourceHealth()]);
  const body = digest ? stripSection(stripSection(digest.body_md, "Source health"), "LLM quota use") : "";
  return (
    <>
      <StaleBanner sources={sources} now={new Date()} />
      <Page
        title="This week"
        description={o.week ? `Scores for the week ending ${o.week}.` : "No week has been scored yet."}
      >
        <KpiRibbon>
          <Kpi
            label="New candidates"
            value={o.buckets.candidate}
            hint="strong evidence, not priced in"
            href="/candidates"
            tone={o.buckets.candidate > 0 ? "up" : undefined}
          />
          <Kpi label="Early" value={o.buckets.early} hint="evidence building" href="/candidates?bucket=early" />
          <Kpi label="Priced-in" value={o.buckets.priced_in} hint="evidence already in the price" href="/candidates?bucket=priced_in" />
          <Kpi label="Theses to review" value={o.review} hint="need your verdict" href="/theses" tone={o.review > 0 ? "warn" : undefined} />
          <Kpi label="Open positions" value={o.position} hint="theses you hold" href="/theses" />
        </KpiRibbon>
        <Section title={digest ? digest.title : "Weekly digest"} id="digest">
          {digest ? (
            <Markdown text={body} />
          ) : (
            <Empty>No digest yet. The weekly run writes one each Saturday, after it scores the universe.</Empty>
          )}
        </Section>
      </Page>
    </>
  );
}
