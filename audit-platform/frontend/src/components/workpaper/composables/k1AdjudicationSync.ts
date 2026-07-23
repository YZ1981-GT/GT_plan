/**
 * K1-1 ← K1-2 取数同步
 */
import { DEFAULT_K2_AGING_BUCKETS } from './k1PolicyCrossHelpers'
import {
  classifyK1Nature,
  classifyK1Portfolio,
  K1_AGING_COUNT,
  K1_NATURE_COUNT,
  K1_PORTFOLIO_COUNT,
} from './k1AdjudicationModel'

const AGING_SEG_KEYS = ['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'] as const

export interface K1DetailRowLike {
  endBalance: number
  badDebtProvision: number
  stage: number
  nature: string
  agingAudited?: Record<string, number>
}

export interface K1AdjSyncAmounts {
  portfolioGross: number[]
  portfolioProvision: number[]
  agingGross: number[]
  agingProvision: number[]
  natureGross: number[]
  natureProvision: number[]
  detailSubtotal: number
  detailProvisionSubtotal: number
}

function emptyArr(n: number): number[] {
  return Array(n).fill(0)
}

export function aggregateK12ForK11(rows: K1DetailRowLike[]): K1AdjSyncAmounts {
  const portfolioGross = emptyArr(K1_PORTFOLIO_COUNT)
  const portfolioProvision = emptyArr(K1_PORTFOLIO_COUNT)
  const agingGross = emptyArr(K1_AGING_COUNT)
  const agingProvision = emptyArr(K1_AGING_COUNT)
  const natureGross = emptyArr(K1_NATURE_COUNT)
  const natureProvision = emptyArr(K1_NATURE_COUNT)

  let detailSubtotal = 0
  let detailProvisionSubtotal = 0

  for (const row of rows) {
    const end = Number(row.endBalance) || 0
    const prov = Number(row.badDebtProvision) || 0
    detailSubtotal += end
    detailProvisionSubtotal += prov

    const pf = classifyK1Portfolio(Number(row.stage) || 1)
    const pfIdx = pf === 'individual' ? 0 : 1
    portfolioGross[pfIdx] += end
    portfolioProvision[pfIdx] += prov

    const natKey = classifyK1Nature(row.nature)
    const natIdx = ['margin', 'deposit', 'petty', 'intercompany', 'other-nature'].indexOf(natKey)
    if (natIdx >= 0) {
      natureGross[natIdx] += end
      natureProvision[natIdx] += prov
    }

    const aging = row.agingAudited || {}
    AGING_SEG_KEYS.forEach((key, i) => {
      if (i >= K1_AGING_COUNT) return
      const amt = Number(aging[key]) || 0
      agingGross[i] += amt
      if (detailSubtotal > 0 && end > 0) {
        agingProvision[i] += prov * (amt / end)
      }
    })
  }

  return {
    portfolioGross,
    portfolioProvision,
    agingGross,
    agingProvision,
    natureGross,
    natureProvision,
    detailSubtotal,
    detailProvisionSubtotal,
  }
}

export function agingBucketLabels(): string[] {
  return [...DEFAULT_K2_AGING_BUCKETS]
}
