/** G12-2 净敞口套期收益明细 — 公式与校验（对齐 Excel 明细表 G12-2） */
import { parseNum } from './useG12FormulaEngine'

export type G12NetHedgeDetailRowKind = 'fv_allocation' | 'amortization'

export interface G12NetHedgeDetailCalcRow {
  rowKind: G12NetHedgeDetailRowKind
  instrumentFvCumulative: number
  salesPortion: number
  purchasePortion: number
  hedgeAdjAmortization: number
}

const TOLERANCE = 0.01

/** 校验：销售部分 + 采购部分 ≈ 套期工具累计公允价值变动 */
export function calcFvAllocationCheck(
  instrumentFvCumulative: number,
  salesPortion: number,
  purchasePortion: number,
): boolean {
  return Math.abs(salesPortion + purchasePortion - instrumentFvCumulative) <= TOLERANCE
}

/** 净敞口套期损益：FV 分配行取销售部分；摊销行取套期调整摊销 */
export function calcNetHedgePnl(row: G12NetHedgeDetailCalcRow): number {
  if (row.rowKind === 'amortization') return parseNum(row.hedgeAdjAmortization)
  return parseNum(row.salesPortion)
}

export interface G12NetHedgeDetailTotals {
  instrumentFvCumulative: number
  salesPortion: number
  purchasePortion: number
  hedgeAdjAmortization: number
  netHedgePnl: number
  fvCheckFailCount: number
}

export function summarizeG12NetHedgeDetailRows(
  rows: G12NetHedgeDetailCalcRow[],
): G12NetHedgeDetailTotals {
  let instrumentFvCumulative = 0
  let salesPortion = 0
  let purchasePortion = 0
  let hedgeAdjAmortization = 0
  let netHedgePnl = 0
  let fvCheckFailCount = 0

  for (const r of rows) {
    if (r.rowKind === 'amortization') {
      hedgeAdjAmortization += parseNum(r.hedgeAdjAmortization)
      netHedgePnl += calcNetHedgePnl(r)
      continue
    }
    instrumentFvCumulative += parseNum(r.instrumentFvCumulative)
    salesPortion += parseNum(r.salesPortion)
    purchasePortion += parseNum(r.purchasePortion)
    netHedgePnl += calcNetHedgePnl(r)
    if (!calcFvAllocationCheck(r.instrumentFvCumulative, r.salesPortion, r.purchasePortion)) {
      fvCheckFailCount += 1
    }
  }

  return {
    instrumentFvCumulative,
    salesPortion,
    purchasePortion,
    hedgeAdjAmortization,
    netHedgePnl,
    fvCheckFailCount,
  }
}
