// The Company page's chart rows (BRIEF §6) come from company_series: the weekly signals run computes each quarter
// with the §4.6 definitions (pipeline/signals/weekly.py series_points), so the charts can't disagree with the signals
// and the screener (M7 review R1-F5). Nothing here recomputes a metric.

export interface QuarterRow {
  period_end: string;
  revenue: number | null;
  op_income: number | null;
  net_income: number | null;
  pretax_income: number | null;
  tax_expense: number | null;
  cfo: number | null;
  capex: number | null;
  da: number | null;
  total_assets: number | null;
  cash: number | null;
  total_debt: number | null;
  equity: number | null;
  rpo: number | null;
  diluted_shares: number | null;
  shares_outstanding: number | null;
}

/** A point of company_series.points (pipeline/signals/weekly.py series_points); a metric without a value is left
 * out. */
export interface SeriesPoint {
  period_end: string;
  revenue_ttm?: number;
  opm?: number;
  roic?: number;
  incremental_roic?: number;
  ccr?: number;
  nd_to_ebitda?: number;
  diluted_shares?: number;
  rpo?: number;
  order_book?: number; // S1's order book: RPO where the filer tags it, else the verified backlog facts (M7 review R2-F5)
}

export interface Point {
  period: string;
  revenue: number | null;
  opm: number | null;
  roic: number | null;
  incremental_roic: number | null;
  ccr: number | null;
  shares: number | null;
  nd_ebitda: number | null;
  order_book: number | null;
}

/** The chart rows, oldest first, with a gap (null) where the pipeline had no value. */
export function chartRows(points: readonly SeriesPoint[]): Point[] {
  const v = (x: number | undefined) => (typeof x === "number" && Number.isFinite(x) ? x : null);
  return [...points]
    .sort((a, b) => a.period_end.localeCompare(b.period_end))
    .map((p) => ({
      period: p.period_end,
      revenue: v(p.revenue_ttm),
      opm: v(p.opm),
      roic: v(p.roic),
      incremental_roic: v(p.incremental_roic),
      ccr: v(p.ccr),
      shares: v(p.diluted_shares),
      nd_ebitda: v(p.nd_to_ebitda),
      order_book: v(p.order_book),
    }));
}
