// Display series for the Company page's charts (BRIEF §6), from fundamentals_display_v rows. Display only: the
// signals use pipeline/signals/series.py. TTM sums need 4 consecutive quarters; ratios need a positive base.

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

export interface Point {
  period: string;
  revenue: number | null;
  opm: number | null;
  roic: number | null;
  incremental_roic: number | null;
  ccr: number | null;
  shares: number | null;
  nd_ebitda: number | null;
  rpo: number | null;
}

const TAX = { us: 0.21, in: 0.25 } as const;

function ttm(rows: QuarterRow[], i: number, key: keyof QuarterRow): number | null {
  if (i < 3) return null;
  let sum = 0;
  for (let k = i - 3; k <= i; k++) {
    const v = rows[k]?.[key];
    if (typeof v !== "number") return null;
    sum += v;
  }
  return sum;
}

function taxRate(rows: QuarterRow[], i: number, market: "us" | "in"): number {
  const tax = ttm(rows, i, "tax_expense");
  const pre = ttm(rows, i, "pretax_income");
  if (tax === null || pre === null || pre <= 0) return TAX[market];
  return Math.min(0.35, Math.max(0.1, tax / pre));
}

function investedCapital(r: QuarterRow | undefined): number | null {
  if (!r || r.equity === null || r.cash === null || r.total_assets === null) return null;
  return Math.max((r.total_debt ?? 0) + r.equity - r.cash, 0.05 * r.total_assets);
}

export function series(input: QuarterRow[], market: "us" | "in"): Point[] {
  const rows = [...input].sort((a, b) => a.period_end.localeCompare(b.period_end));
  return rows.map((r, i) => {
    const rev = ttm(rows, i, "revenue");
    const op = ttm(rows, i, "op_income");
    const ni = ttm(rows, i, "net_income");
    const cfo = ttm(rows, i, "cfo");
    const da = ttm(rows, i, "da");
    const nopat = op === null ? null : op * (1 - taxRate(rows, i, market));
    const ic = investedCapital(r);
    const icBack = investedCapital(rows[i - 4]);
    const opBack = i >= 4 ? ttm(rows, i - 4, "op_income") : null;
    const nopatBack = opBack === null ? null : opBack * (1 - taxRate(rows, i - 4, market));
    const ebitda = op !== null && da !== null ? op + da : null;
    const nd = r.cash === null ? null : (r.total_debt ?? 0) - r.cash;
    return {
      period: r.period_end,
      revenue: rev,
      opm: rev !== null && rev > 0 && op !== null ? op / rev : null,
      roic: nopat !== null && ic !== null && ic > 0 ? nopat / ic : null,
      incremental_roic:
        nopat !== null && nopatBack !== null && ic !== null && icBack !== null && ic - icBack > 0
          ? (nopat - nopatBack) / (ic - icBack)
          : null,
      ccr: cfo !== null && ni !== null && ni > 0 ? cfo / ni : null,
      shares: r.diluted_shares ?? r.shares_outstanding,
      nd_ebitda: nd !== null && ebitda !== null && ebitda > 0 ? nd / ebitda : null,
      rpo: r.rpo,
    };
  });
}
