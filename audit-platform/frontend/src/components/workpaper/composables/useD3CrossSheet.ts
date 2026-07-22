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
  aggregateAgingByKeys,
  collectAgingKeys,
  parseNum,
  type DetailRowForFormula,
} from './useD3FormulaEngine'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from './useD3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD3CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /**
   * 项目账龄配置段（来自 useAgingConfig，subject='D3'）。
   * 提供时账龄聚合/长期筛选严格按项目配置的段进行（支持 THREE_YEAR/FIVE_YEAR/CUSTOM）；
   * 未提供时从明细数据中收集段 key 兜底，仍避免固定 4 段导致的取零。
   */
  segments?: Ref<AgingSegment[]>
}

/** ">1年" 段判定阈值（天）：dayFrom ≥ 366 视为账龄超过 1 年 */
const OVER_ONE_YEAR_DAY_FROM = 366

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
  const { allResponses, segments } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── 解析 D3-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<D3DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('D3-det-rows')
    return safeParseRows<D3DetailRowRaw>(resp?.remark)
  })

  // ─── 有效账龄段（项目配置优先，数据兜底，最终 THREE_YEAR 默认） ──────────

  /**
   * 有效账龄段：优先用项目账龄配置（segments），否则从明细数据收集 key 兜底，
   * 再退到 THREE_YEAR 预设。保证账龄聚合/长期筛选覆盖项目实际使用的段。
   */
  const agingSegments: ComputedRef<AgingSegment[]> = computed(() => {
    if (segments?.value?.length) return segments.value
    const dataKeys = collectAgingKeys(
      detailRows.value.map(r => ({
        agingPrior: (r.agingPrior ?? null) as Record<string, number> | null,
        agingAudited: (r.agingAudited ?? null) as Record<string, number> | null,
      })),
    )
    if (!dataKeys.length) return PRESET_SEGMENTS.THREE_YEAR
    // 数据兜底：无法获知天数边界，首段视为 1 年以内，其余视为 >1 年
    return dataKeys.map((k, i) => ({
      key: k,
      label: k,
      dayFrom: i === 0 ? 0 : OVER_ONE_YEAR_DAY_FROM,
      dayTo: null,
    }))
  })

  const agingSegmentKeys = computed<string[]>(() => agingSegments.value.map(s => s.key))

  /** 账龄超 1 年的段 key（dayFrom ≥ 366） */
  const overOneYearKeys = computed<string[]>(() =>
    agingSegments.value.filter(s => s.dayFrom >= OVER_ONE_YEAR_DAY_FROM).map(s => s.key),
  )

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

  // ─── D3-2 → D3-1 按账龄聚合（segment-driven，替代固定 4 段） ────────────

  /**
   * agingByKey: 按项目账龄配置段聚合期末审定(current)与期初审定(prior)。
   * 以段 key 为索引，供 D3-1 审定表「按账龄分类」与附注国企「按账龄」取数。
   * 支持 THREE_YEAR/FIVE_YEAR/CUSTOM 任意段数，不再局限固定 within1/y1to2/y2to3/over3。
   */
  const agingByKey: ComputedRef<{ current: Record<string, number>; prior: Record<string, number> }> = computed(() => {
    const rows = detailRows.value.map(r => ({
      agingPrior: (r.agingPrior ?? null) as Record<string, number> | null,
      agingAudited: (r.agingAudited ?? null) as Record<string, number> | null,
    }))
    return aggregateAgingByKeys(rows, agingSegmentKeys.value)
  })

  // ─── D3-2 → D3-5 筛选账龄>1年行（segment-driven） ───────────────────

  /**
   * longTermRows: 筛选审定账龄中「>1年段(dayFrom≥366)合计 > 0」的行。
   * 用于 D3-5 长期检查表"从D3-2导入"功能。账龄描述由实际配置段标签拼接。
   */
  const longTermRows: ComputedRef<LongTermImportRow[]> = computed(() => {
    const overKeys = overOneYearKeys.value
    const segLabelByKey = new Map(agingSegments.value.map(s => [s.key, s.label]))
    return detailRows.value
      .filter(row => {
        const audited = (row.agingAudited ?? {}) as Record<string, number>
        const overSum = overKeys.reduce((sum, k) => sum + parseNum(audited[k]), 0)
        return overSum > 0
      })
      .map(row => {
        const audited = (row.agingAudited ?? {}) as Record<string, number>
        // 保留 4 段兼容字段供旧消费者读取（LongTermImportRow.agingAudited 类型）
        const aging = {
          within1: parseNum(audited.within1),
          y1to2: parseNum(audited.y1to2),
          y2to3: parseNum(audited.y2to3),
          over3: parseNum(audited.over3),
        }
        // 账龄描述：拼接有金额的 >1年 配置段标签
        const parts = overKeys
          .filter(k => parseNum(audited[k]) > 0)
          .map(k => segLabelByKey.get(k) || k)
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
    // segment-driven 账龄聚合 + 有效段（支持自定义账龄配置）
    agingByKey,
    agingSegments,
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
