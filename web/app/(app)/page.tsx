import { Markdown } from "@/components/markdown";
import { Empty, Page, Section } from "@/components/page";
import { StaleBanner } from "@/components/stale";
import { GroupSection } from "@/components/thesis-list";
import { requireUser } from "@/lib/auth";
import { ensureReviews, latestDigest, sourceHealth, theses, thesisFigures } from "@/lib/data";
import { homeSections } from "@/lib/home";
import { group, markMoved } from "@/lib/theses";

export const metadata = { title: "This week" };

// BRIEF §6 Home (overhaul PR 5, the only PR that changes it): the funnel line as one terminal strip, To do (the
// Theses screen's Needs you group, read live), What changed, and the stale-data banner when a US source is late. The
// funnel and What changed are the digest's own sections (lib/home.ts), so Home and the issue read the same; with no
// KPI cards, a count here can't contradict the digest.
export default async function Home() {
  await requireUser(); // besides the middleware and the layout (M7 review R1-F10)
  const [digest, sources, first] = await Promise.all([latestDigest(), sourceHealth(), theses()]);
  const all = markMoved(first, await ensureReviews(first)); // as the Theses screen does, so both list the same
  const needs = all.filter((t) => group(t) === "needs");
  const figures = await thesisFigures(needs);
  const { funnel, changed } = homeSections(digest?.body_md ?? "");
  return (
    <Page title="This week" description={digest ? `${digest.title} · week ending ${digest.week_end}` : "No digest yet."}>
      <section aria-labelledby="funnel" className="rounded-md border border-line bg-panel px-4 py-2.5">
        <h2 id="funnel" className="sr-only">
          Funnel
        </h2>
        {funnel ? (
          <div className="num text-[13px] text-fg [&_.prose-md]:max-w-none [&_.prose-md]:text-[13px] [&_.prose-md_p]:my-0">
            <Markdown text={funnel} />
          </div>
        ) : (
          <p className="text-[13px] text-muted">No digest yet. The weekly run writes one each Saturday, after it scores the universe.</p>
        )}
      </section>
      <GroupSection group="needs" title="To do" id="todo" list={needs} figures={figures} />
      <Section title="What changed" id="changed" description="Each company's biggest change this week and why, then new verified facts and guidance or backlog changes.">
        {changed ? <Markdown text={changed} /> : <Empty>Nothing to compare yet: What changed comes with the weekly digest.</Empty>}
      </Section>
      <div className="overflow-hidden rounded-md">
        <StaleBanner sources={sources} now={new Date()} />
      </div>
    </Page>
  );
}
