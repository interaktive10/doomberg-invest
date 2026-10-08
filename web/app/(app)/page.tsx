import { Markdown } from "@/components/markdown";
import { Empty, Page, Section, Stat } from "@/components/page";
import { requireUser } from "@/lib/auth";
import { stripSection } from "@/lib/cards";
import { latestDigest, overview } from "@/lib/data";

export const metadata = { title: "This week" };

// BRIEF §6 Home, simplified (Manzoor, 2026-10-08): what needs a look this week and the weekly digest. Source health
// and LLM quota use moved to Settings; the stale-data banner (the layout's) still shows here when a source is late.
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, o] = await Promise.all([latestDigest(), overview()]);
  const body = digest ? stripSection(stripSection(digest.body_md, "Source health"), "LLM quota use") : "";
  return (
    <Page
      title="This week"
      description={o.week ? `Scores for the week ending ${o.week}. Research only: no orders, no price alerts.` : "No week has been scored yet."}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="New candidates" value={o.buckets.candidate} hint="strong evidence, not priced in" href="/candidates" />
        <Stat label="Theses to review" value={o.review} hint="need your verdict" href="/theses" />
        <Stat label="Open positions" value={o.position} hint="theses you hold" href="/theses" />
      </div>
      <Section title={digest ? digest.title : "Weekly digest"} id="digest">
        {digest ? (
          <Markdown text={body} />
        ) : (
          <Empty>No digest yet. The weekly run writes one each Saturday, after it scores the universe.</Empty>
        )}
      </Section>
    </Page>
  );
}
