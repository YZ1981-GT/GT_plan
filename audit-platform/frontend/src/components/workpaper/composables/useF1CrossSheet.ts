/**
 * useF1CrossSheet — F1 预付账款跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('F1-det-rows')?.remark 存 JSON 数组，try/catch 解析。
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 5.1
 * Requirements: 2.1, 2.2, 9.2, 10.4, 12.2, 12.3, 13.2, 13.3
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  aggregateByNature,
  aggregateByAging,
  parseNum,
  DEFAULT_F1_AGING_KEYS,
  type DetailRowForFormula,
} from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { resolveAgingLabel, formatAgingAmountHint } from './agingPresets'

function collectAgingKeys(rows: F1DetailRowRaw[]): string[] {
  const keys = new Set<string>()
  for (const row of rows) {
    Object.keys(row.agingAudited || {}).forEach(k => keys.add(k))
    Object.keys(row.agingPrior || {}).forEach(k => keys.add(k))
  }
  if (keys.size === 0) {
    DEFAULT_F1_AGING_KEYS.forEach(k => keys.add(k))
  }
  return [...keys]
}

function sumAgingMap(aging: Record<string, number> | undefined, keys: string[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const k of keys) result[k] = parseNum(aging?.[k])
  return result
}

const OVER_ONE_YEAR_DAY_FROM = 366

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseF1CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /** 项目账龄段（可选）；有则优先用于超1年筛选与标签 */
  segments?: Ref<AgingSegment[]>
}

/** F1-2 明细行原始 JSON 结构（remark 中存储） */
export interface F1DetailRowRaw {
  rowId: string
  customerName: string
  companyCode?: string
  nature: string
  relationType: string
  priorUnadjusted?: number
  priorAdjustment?: number
  priorReclass?: number
  agingPrior?: Record<string, number>
  debit?: number
  credit?: number
  entityReclass?: number
  endAje?: number
  endRje?: number
  endAudited?: number
  priorAudited?: number
  agingAudited?: Record<string, number>
  isConfirmed?: string
  postPeriodSettlement?: number
  remark?: string
}

/** F1-3 调整分录行原始 JSON 结构 */
export interface F1AdjustmentRowRaw {
  rowId: string
  description?: string
  category?: string
  reportItem?: string
  accountName?: string
  noteItem?: string
  placeholder?: string
  debitAmount?: number
  creditAmount?: number
  indexRef?: string
  remark?: string
}

/** F1-7 期后结转行原始 JSON 结构 */
export interface D3PostPeriodRowRaw {
  rowId: string
  customerName?: string
  supplierName?: string
  creditAmount?: number
}

/** 长期检查导入行 */
export interface LongTermImportRow {
  customerName: string
  endAudited: number
  agingDescription: string
  agingAudited: Record<string, number>
}

/** 关联方检查导入行 */
export interface RelatedPartyImportRow {
  customerName: string
  relationType: string
  priorAudited: number
  endAudited: number
  debit: number
  credit: number
  nature?: string
  agingDescription?: string
  postPeriodSettlement?: number
}

/** 附注数据结构 */
export interface DisclosureSourceData {
  natureAggregation: Record<string, { prior: number; current: number }>
  /** 当期段 key + prior_{key} */
  agingAggregation: Record<string, number>
  longTermRows: LongTermImportRow[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1CrossSheet(options: UseF1CrossSheetOptions) {
  const { allResponses, segments } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── 解析 F1-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<F1DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('F1-det-rows')
    return safeParseRows<F1DetailRowRaw>(resp?.remark)
  })

  /**
   * 有效账龄段：优先项目配置，否则从明细 key 兜底，再兜底 THREE_YEAR
   */
  const agingSegments: ComputedRef<AgingSegment[]> = computed(() => {
    if (segments?.value?.length) return segments.value
    const keys = collectAgingKeys(detailRows.value)
    if (keys.length) {
      const fromPreset = PRESET_SEGMENTS.FIVE_YEAR.concat(PRESET_SEGMENTS.THREE_YEAR)
      const byKey = new Map(fromPreset.map(s => [s.key, s]))
      return keys.map((k) => byKey.get(k) || {
        key: k,
        label: resolveAgingLabel(k),
        dayFrom: k === 'within1' ? 0 : OVER_ONE_YEAR_DAY_FROM,
        dayTo: null,
      })
    }
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const overOneYearKeys = computed(() => {
    const segs = agingSegments.value
    const byDay = segs.filter(s => s.dayFrom >= OVER_ONE_YEAR_DAY_FROM).map(s => s.key)
    if (byDay.length) return byDay
    // 自定义段（dayFrom 未维护，全 0）：首段视为最短账龄，其余段计入「超 1 年」
    return segs.slice(1).map(s => s.key)
  })

  /** 将原始行转为公式引擎所需的 DetailRowForFormula 结构 */
  const detailRowsForFormula = computed<DetailRowForFormula[]>(() => {
    const keys = collectAgingKeys(detailRows.value)
    return detailRows.value.map(row => ({
      nature: row.nature || '',
      endAudited: parseNum(row.endAudited),
      priorAudited: parseNum(row.priorAudited),
      agingAudited: sumAgingMap(row.agingAudited, keys),
    }))
  })

  // ─── F1-2 → F1-1 按款项性质聚合 ──────────────────────────────────────

  /**
   * natureAggregation: 按款项性质分组，聚合 endAudited 和 priorAudited
   * 用于 F1-1 审定表"按性质分类"区块
   */
  const natureAggregation: ComputedRef<Record<string, { prior: number; current: number }>> = computed(() => {
    const rows = detailRowsForFormula.value
    const currentByNature = aggregateByNature(rows, 'endAudited')
    const priorByNature = aggregateByNature(rows, 'priorAudited')

    const allNatures = new Set([...Object.keys(currentByNature), ...Object.keys(priorByNature)])
    const result: Record<string, { prior: number; current: number }> = {}
    for (const nature of allNatures) {
      result[nature] = {
        current: currentByNature[nature] || 0,
        prior: priorByNature[nature] || 0,
      }
    }
    return result
  })

  // ─── F1-2 → F1-1 按审定账龄聚合 ──────────────────────────────────────

  /**
   * agingAggregation: 按审定账龄段动态聚合
   * 用于 F1-1 审定表"按账龄分类"区块
   * 返回：{ [segmentKey]: current, prior_${segmentKey}: prior }
   */
  const agingAggregation: ComputedRef<Record<string, number>> = computed(() => {
    // 🔴 键集合 = 当前生效账龄段 ∪ 明细行实际键：
    //   保证 F1-1 审定表/附注按当前枚举段（3年/5年/自定义）读到每一段（缺段返 0 而非 undefined），
    //   同时不丢弃明细里尚未 remap 的历史段（避免金额在切换瞬间消失）。
    const keys = Array.from(
      new Set([
        ...agingSegments.value.map(s => s.key),
        ...collectAgingKeys(detailRows.value),
      ]),
    )
    const currentAging = aggregateByAging(detailRowsForFormula.value, keys)

    const result: Record<string, number> = { ...currentAging }
    for (const k of keys) {
      result[`prior_${k}`] = 0
    }
    for (const row of detailRows.value) {
      for (const k of keys) {
        result[`prior_${k}`] += parseNum(row.agingPrior?.[k])
      }
    }
    return result
  })

  // ─── F1-2 → F1-5 筛选账龄>1年行 ─────────────────────────────────────

  /**
   * longTermRows: 筛选审定账龄中「>1年段」合计 > 0 的行
   * 用于 F1-5 长期检查表"从F1-2导入"功能；描述用枚举 label
   */
  const longTermRows: ComputedRef<LongTermImportRow[]> = computed(() => {
    const keys = agingSegments.value.map(s => s.key)
    const over1Keys = overOneYearKeys.value
    const segs = agingSegments.value
    return detailRows.value
      .filter(row => {
        const over1 = over1Keys.reduce((s, k) => s + parseNum(row.agingAudited?.[k]), 0)
        return over1 > 0
      })
      .map(row => {
        const aging = sumAgingMap(row.agingAudited, keys)
        const parts: string[] = []
        for (const k of over1Keys) {
          if (aging[k] > 0) parts.push(resolveAgingLabel(k, segs))
        }
        return {
          customerName: row.customerName || '',
          endAudited: parseNum(row.endAudited),
          agingDescription: parts.join('、') || '1年以上',
          agingAudited: aging,
        }
      })
  })

  // ─── F1-2 → F1-6 筛选关联方行 ────────────────────────────────────────

  /**
   * relatedPartyRows: 筛选 relationType !== '非关联方' 且 relationType !== '' 的行
   * 用于 F1-6 关联方检查表"从F1-2导入"功能
   */
  const relatedPartyRows: ComputedRef<RelatedPartyImportRow[]> = computed(() => {
    const segs = agingSegments.value
    return detailRows.value
      .filter(row => row.relationType !== '非关联方' && row.relationType !== '')
      .map(row => ({
        customerName: row.customerName || '',
        relationType: row.relationType,
        priorAudited: parseNum(row.priorAudited),
        endAudited: parseNum(row.endAudited),
        debit: parseNum(row.debit),
        credit: parseNum(row.credit),
        nature: row.nature || '',
        agingDescription: formatAgingAmountHint(row.agingAudited, segs),
        postPeriodSettlement: parseNum(row.postPeriodSettlement),
      }))
  })

  // ─── F1-3 → F1-1 AJE/RJE 汇总 ───────────────────────────────────────

  /** 解析 F1-3 调整分录行数据 */
  const adjustmentRows = computed<F1AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('F1-aje-rows')
    return safeParseRows<F1AdjustmentRowRaw>(resp?.remark)
  })

  /**
   * adjustmentTotals: 从F1-3行汇总 AJE/RJE 净额
   * category='账项调整' → AJE
   * category='重分类调整' → RJE
   *
   * 🔴 预付账款(1123)是资产借方科目：借方调整=调增审定数、贷方调整=调减审定数，
   * 故取**净额 debitAmount − creditAmount**（此前只累加 debitAmount，贷方调减被整段
   * 丢弃 → F1-1「审定调整 vs F1-3 汇总」勾稽口径错、调减分录永远对不上）。
   */
  const adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }> = computed(() => {
    let ajeTotal = 0
    let rjeTotal = 0

    for (const row of adjustmentRows.value) {
      const amount = parseNum(row.debitAmount) - parseNum(row.creditAmount)
      if (row.category === '账项调整') {
        ajeTotal += amount
      } else if (row.category === '重分类调整') {
        rjeTotal += amount
      }
    }

    return { ajeTotal, rjeTotal }
  })

  // ─── F1-1 → 附注 ─────────────────────────────────────────────────────

  /**
   * adjudicationForDisclosure: 审定表数据供附注披露引用
   * 组合 natureAggregation + agingAggregation + longTermRows
   */
  const adjudicationForDisclosure: ComputedRef<DisclosureSourceData> = computed(() => {
    return {
      natureAggregation: natureAggregation.value,
      agingAggregation: agingAggregation.value,
      longTermRows: longTermRows.value,
    }
  })

  // ─── F1-7 期后结转 → F1-2 联动 ───────────────────────────────────────

  /**
   * postPeriodSettlementSync: 从F1-7 (2)期后结转区块按客户聚合贷方金额
   * 供 F1-2 Z列（期后结转）交叉验证使用
   */
  const postPeriodSettlementSync: ComputedRef<{ byCustomer: Record<string, number>; total: number }> = computed(() => {
    const resp = allResponses.value.get('F1-vc-post-rows')
    const rows = safeParseRows<D3PostPeriodRowRaw>(resp?.remark)

    const byCustomer: Record<string, number> = {}
    let total = 0

    for (const row of rows) {
      const name = row.supplierName || row.customerName || ''
      const amount = parseNum(row.creditAmount)
      if (name) {
        byCustomer[name] = (byCustomer[name] || 0) + amount
      }
      total += amount
    }

    return { byCustomer, total }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  /** F1-2 明细行数（>0 表示明细已编制：审定表据此决定是否用聚合值 seed 空白行） */
  const detailRowCount: ComputedRef<number> = computed(() => detailRows.value.length)

  return {
    // F1-2 → F1-1 聚合
    natureAggregation,
    agingAggregation,
    agingSegments,
    detailRowCount,
    // F1-2 → F1-5 筛选
    longTermRows,
    // F1-2 → F1-6 筛选
    relatedPartyRows,
    // F1-3 → F1-1 AJE/RJE
    adjustmentTotals,
    // F1-1 → 附注
    adjudicationForDisclosure,
    // F1-7 → F1-2 期后结转
    postPeriodSettlementSync,
    // 状态
    crossSheetStatus,
  }
}

export default useF1CrossSheet
