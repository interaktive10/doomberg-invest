// Themes (pipeline/reports/themes.py writes reports('themes', week); docs/SPEC_ISSUES.md 67): the body's shape and the
// words the Themes screen shows. Pure, so tests/themes.test.ts covers it.

export interface ThemeEvidence {
  id: string;
  company_id: string;
  code: string | null;
  name: string;
  what: string;
  move: number;
  price?: number | null;
}

export interface Theme {
  market: "us" | "in";
  industry: string;
  title: string;
  why: string;
  wrong_if: string;
  confidence: "low" | "medium" | "high";
  evidence: ThemeEvidence[];
  share: number;
  with_demand: number;
  companies: number;
  median_move: number;
  early: boolean;
}

export interface IndustryRow {
  market: "us" | "in";
  industry: string;
  companies: number;
  with_demand: number;
  share: number;
  facts: number;
  order_book: number;
  accelerating: number;
  median_move: number;
}

export interface EarlierCall {
  week: string;
  market: string;
  industry: string;
  title: string;
  since: number | null;
}

export interface Review {
  market: string;
  industry: string;
  decision: "keep" | "drop";
  reason: string;
}

export interface ThemesReport {
  week: string;
  medians: Partial<Record<"us" | "in", number>>;
  industries: IndustryRow[];
  candidates: number;
  themes: Theme[];
  reviews: Review[];
  note: string;
  scorecard: EarlierCall[];
  answered: boolean;
}

/** A fact's kind in plain words ("order_win: a $40M transformer order" -> "Order win: a $40M transformer order"). */
export function evidenceLine(what: string): string {
  const m = /^([a-z_]+): (.*)$/s.exec(what);
  if (!m) return what.charAt(0).toUpperCase() + what.slice(1);
  const kind = m[1]!.replace(/_/g, " ");
  return `${kind.charAt(0).toUpperCase()}${kind.slice(1)}: ${m[2]}`;
}

/** The review of an earlier call, if this week's pass gave one. */
export function reviewOf(reviews: readonly Review[], c: Pick<EarlierCall, "market" | "industry">): Review | undefined {
  return reviews.find((r) => r.market === c.market && r.industry === c.industry);
}

/** A demand bar's width: the share of companies with evidence, as a percent. */
export function sharePct(share: number): number {
  return Math.max(0, Math.min(100, Math.round(share * 100)));
}
