/**
 * K1-1 ← K1-2 取数同步
 *
 * 🔴 账龄按**段 key** 取值，不按下标猜：原实现硬编码
 * `['within1','y1to2','y2to3','y3to4','y4to5','over5']`（5 年段），项目配 3 年段
 * （`['within1','y1to2','y2to3','over3']`）时 `over3` 永远读不到 → K1-1 账龄分布
 * 少一档金额、多三行空行。
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/ R5 / Property 5
 */
import type { AgingSegment } from '@/composables/useAgingConfig'
import {
  classifyK1Nature,
  classifyK1Portfolio,
  buildK1AgingRowDefs,
  k1AgingSegmentKeys,
  K1_NATURE_COUNT,
  K1_PORTFOLIO_COUNT,
} from './k1AdjudicationModel'

/** 5 年段段 key（默认值；仅在调用方未传 segments 时使用） */
export const K1_DEFAULT_AGING_SEG_KEYS: readonly string[] = k1AgingSegmentKeys()

const NATURE_KEYS = ['margin', 'deposit', 'petty', 'intercompany', 'other-nature'] as const

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
  /** 本次聚合实际使用的账龄段 key（供调用方对齐行序） */
  agingSegmentKeys: string[]
}

function emptyArr(n: number): number[] {
  return Array(n).fill(0)
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * K1-2 明细 → K1-1 各分布区块金额。
 *
 * @param rows K1-2 明细行
 * @param segments 项目账龄段（`useAgingConfig(projectId,'K1').segments`）；
 *   也接受纯 key 数组。缺省用 K1 默认 5 年段（与改动前逐字等价）。
 */
export function aggregateK12ForK11(
  rows: K1DetailRowLike[],
  segments?: readonly AgingSegment[] | readonly string[] | null,
): K1AdjSyncAmounts {
  const segKeys: string[] = (() => {
    if (!segments || !segments.length) return [...K1_DEFAULT_AGING_SEG_KEYS]
    const first = segments[0] as unknown
    if (typeof first === 'string') return (segments as readonly string[]).map(String)
    return k1AgingSegmentKeys(segments as readonly AgingSegment[])
  })()

  const portfolioGross = emptyArr(K1_PORTFOLIO_COUNT)
  const portfolioProvision = emptyArr(K1_PORTFOLIO_COUNT)
  const agingGross = emptyArr(segKeys.length)
  const agingProvision = emptyArr(segKeys.length)
  const natureGross = emptyArr(K1_NATURE_COUNT)
  const natureProvision = emptyArr(K1_NATURE_COUNT)

  let detailSubtotal = 0
  let detailProvisionSubtotal = 0

  for (const row of rows || []) {
    const end = _num(row.endBalance)
    const prov = _num(row.badDebtProvision)
    detailSubtotal += end
    detailProvisionSubtotal += prov

    const pf = classifyK1Portfolio(_num(row.stage) || 1)
    const pfIdx = pf === 'individual' ? 0 : 1
    portfolioGross[pfIdx] += end
    portfolioProvision[pfIdx] += prov

    const natKey = classifyK1Nature(row.nature)
    const natIdx = NATURE_KEYS.indexOf(natKey as (typeof NATURE_KEYS)[number])
    if (natIdx >= 0) {
      natureGross[natIdx] += end
      natureProvision[natIdx] += prov
    }

    const aging = row.agingAudited || {}
    segKeys.forEach((key, i) => {
      const amt = _num(aging[key])
      if (!amt) return
      agingGross[i] += amt
      // 坏账按账龄占比分摊（明细行自身口径，与 detailSubtotal 无关）
      if (end !== 0) agingProvision[i] += prov * (amt / end)
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
    agingSegmentKeys: segKeys,
  }
}

/** 账龄档标签（跟随项目账龄段；缺省 5 年段） */
export function agingBucketLabels(
  segments?: readonly AgingSegment[] | null,
): string[] {
  return buildK1AgingRowDefs(segments)
    .filter((d) => !d.isSubtotal)
    .map((d) => d.label)
}
