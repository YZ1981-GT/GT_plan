/**
 * useD3CrossSheet — D3 预收账款跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('D3-det-rows')?.remark 存 JSON 数组，try/catch 解析。
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 5.1
 * Requirements: 2.1, 2.2, 9.2, 10.4, 12.2, 12.3, 13.2, 13.3
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  aggregateByNature,
  aggregateByAging,
  parseNum,
  type DetailRowForFormula,
} from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD3CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

/** D3-2 明细行原始 JSON 结构（remark 中存储） */
export interface D3DetailRowRaw {
  rowId: string
  customerName: string
  companyCode?: string
  nature: string
  relationType: string
  priorUnadjusted?: number
  priorAdjustment?: number
  priorReclass?: number
  agingPrior?: { within1: number; y1to2: number; y2to3: number; over3: number }
  debit?: number
  credit?: number
  entityReclass?: number
  endAje?: number
  endRje?: number
  endAudited?: number
  priorAudited?: number
  agingAudited?: { within1: number; y1to2: number; y2to3: number; over3: number }
  isConfirmed?: string
  postPeriodSettlement?: number
  remark?: string
}

/** D3-3 调整分录行原始 JSON 结构 */
export interface D3AdjustmentRowRaw {
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

/** D3-7 期后结转行原始 JSON 结构 */
export interface D3PostPeriodRowRaw {
  rowId: string
  customerName: string
  creditAmount?: number
}

/** 长期检查导入行 */
export interface LongTermImportRow {
  customerName: string
  endAudited: number
  agingDescription: string
  agingAudited: { within1: number; y1to2: number; y2to3: number; over3: number }
}

/** 关联方检查导入行 */
export interface RelatedPartyImportRow {
  customerName: string
  relationType: string
  priorAudited: number
  endAudited: number
  debit: number
  credit: number
}

/** 附注数据结构 */
export interface DisclosureSourceData {
  natureAggregation: Record<string, { prior: number; current: number }>
  agingAggregation: {
    within1: number; y1to2: number; y2to3: number; over3: number
    prior_within1: number; prior_y1to2: number; prior_y2to3: number; prior_over3: number
  }
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

export function useD3CrossSheet(options: UseD3CrossSheetOptions) {
  const { allResponses } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── 解析 D3-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<D3DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('D3-det-rows')
    return safeParseRows<D3DetailRowRaw>(resp?.remark)
  })

  /** 将原始行转为公式引擎所需的 DetailRowForFormula 结构 */
  const detailRowsForFormula = computed<DetailRowForFormula[]>(() => {
    return detailRows.value.map(row => ({
      nature: row.nature || '',
      endAudited: parseNum(row.endAudited),
      priorAudited: parseNum(row.priorAudited),
      agingAudited: {
        within1: parseNum(row.agingAudited?.within1),
        y1to2: parseNum(row.agingAudited?.y1to2),
        y2to3: parseNum(row.agingAudited?.y2to3),
        over3: parseNum(row.agingAudited?.over3),
      },
    }))
  })

  // ─── D3-2 → D3-1 按款项性质聚合 ──────────────────────────────────────

  /**
   * natureAggregation: 按款项性质分组，聚合 endAudited 和 priorAudited
   * 用于 D3-1 审定表"按性质分类"区块
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

  // ─── D3-2 → D3-1 按审定账龄聚合 ──────────────────────────────────────

  /**
   * agingAggregation: 按审定账龄 U~X 列聚合
   * 用于 D3-1 审定表"按账龄分类"区块
   * 同时计算期初审定账龄（agingPrior）
   */
  const agingAggregation: ComputedRef<{
    within1: number; y1to2: number; y2to3: number; over3: number
    prior_within1: number; prior_y1to2: number; prior_y2to3: number; prior_over3: number
  }> = computed(() => {
    const rows = detailRowsForFormula.value
    const currentAging = aggregateByAging(rows)

    // 期初账龄聚合：从原始行的 agingPrior 字段
    let prior_within1 = 0
    let prior_y1to2 = 0
    let prior_y2to3 = 0
    let prior_over3 = 0
    for (const row of detailRows.value) {
      prior_within1 += parseNum(row.agingPrior?.within1)
      prior_y1to2 += parseNum(row.agingPrior?.y1to2)
      prior_y2to3 += parseNum(row.agingPrior?.y2to3)
      prior_over3 += parseNum(row.agingPrior?.over3)
    }

    return {
      ...currentAging,
      prior_within1,
      prior_y1to2,
      prior_y2to3,
      prior_over3,
    }
  })

  // ─── D3-2 → D3-5 筛选账龄>1年行 ─────────────────────────────────────

  /**
   * longTermRows: 筛选审定账龄中 y1to2 + y2to3 + over3 > 0 的行
   * 用于 D3-5 长期检查表"从D3-2导入"功能
   */
  const longTermRows: ComputedRef<LongTermImportRow[]> = computed(() => {
    return detailRows.value
      .filter(row => {
        const y1to2 = parseNum(row.agingAudited?.y1to2)
        const y2to3 = parseNum(row.agingAudited?.y2to3)
        const over3 = parseNum(row.agingAudited?.over3)
        return y1to2 + y2to3 + over3 > 0
      })
      .map(row => {
        const aging = {
          within1: parseNum(row.agingAudited?.within1),
          y1to2: parseNum(row.agingAudited?.y1to2),
          y2to3: parseNum(row.agingAudited?.y2to3),
          over3: parseNum(row.agingAudited?.over3),
        }
        // 构建账龄描述
        const parts: string[] = []
        if (aging.y1to2 > 0) parts.push('1-2年')
        if (aging.y2to3 > 0) parts.push('2-3年')
        if (aging.over3 > 0) parts.push('3年以上')
        return {
          customerName: row.customerName || '',
          endAudited: parseNum(row.endAudited),
          agingDescription: parts.join('、') || '1年以上',
          agingAudited: aging,
        }
      })
  })

  // ─── D3-2 → D3-6 筛选关联方行 ────────────────────────────────────────

  /**
   * relatedPartyRows: 筛选 relationType !== '非关联方' 且 relationType !== '' 的行
   * 用于 D3-6 关联方检查表"从D3-2导入"功能
   */
  const relatedPartyRows: ComputedRef<RelatedPartyImportRow[]> = computed(() => {
    return detailRows.value
      .filter(row => row.relationType !== '非关联方' && row.relationType !== '')
      .map(row => ({
        customerName: row.customerName || '',
        relationType: row.relationType,
        priorAudited: parseNum(row.priorAudited),
        endAudited: parseNum(row.endAudited),
        debit: parseNum(row.debit),
        credit: parseNum(row.credit),
      }))
  })

  // ─── D3-3 → D3-1 AJE/RJE 汇总 ───────────────────────────────────────

  /** 解析 D3-3 调整分录行数据 */
  const adjustmentRows = computed<D3AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('D3-aje-rows')
    return safeParseRows<D3AdjustmentRowRaw>(resp?.remark)
  })

  /**
   * adjustmentTotals: 从D3-3行汇总 AJE/RJE 金额
   * category='账项调整' → AJE
   * category='重分类调整' → RJE
   * 金额取 debitAmount（借方调整=增加审定数）
   */
  const adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }> = computed(() => {
    let ajeTotal = 0
    let rjeTotal = 0

    for (const row of adjustmentRows.value) {
      const amount = parseNum(row.debitAmount)
      if (row.category === '账项调整') {
        ajeTotal += amount
      } else if (row.category === '重分类调整') {
        rjeTotal += amount
      }
    }

    return { ajeTotal, rjeTotal }
  })

  // ─── D3-1 → 附注 ─────────────────────────────────────────────────────

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

  // ─── D3-7 期后结转 → D3-2 联动 ───────────────────────────────────────

  /**
   * postPeriodSettlementSync: 从D3-7 (2)期后结转区块按客户聚合贷方金额
   * 供 D3-2 Z列（期后结转）交叉验证使用
   */
  const postPeriodSettlementSync: ComputedRef<{ byCustomer: Record<string, number>; total: number }> = computed(() => {
    const resp = allResponses.value.get('D3-vc-post-rows')
    const rows = safeParseRows<D3PostPeriodRowRaw>(resp?.remark)

    const byCustomer: Record<string, number> = {}
    let total = 0

    for (const row of rows) {
      const name = row.customerName || ''
      const amount = parseNum(row.creditAmount)
      if (name) {
        byCustomer[name] = (byCustomer[name] || 0) + amount
      }
      total += amount
    }

    return { byCustomer, total }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // D3-2 → D3-1 聚合
    natureAggregation,
    agingAggregation,
    // D3-2 → D3-5 筛选
    longTermRows,
    // D3-2 → D3-6 筛选
    relatedPartyRows,
    // D3-3 → D3-1 AJE/RJE
    adjustmentTotals,
    // D3-1 → 附注
    adjudicationForDisclosure,
    // D3-7 → D3-2 期后结转
    postPeriodSettlementSync,
    // 状态
    crossSheetStatus,
  }
}

export default useD3CrossSheet
