/**
 * useD7CrossSheet — D7 合同负债跨Sheet联动 computed 响应式链
 *
 * 所有跨sheet数据流通过 allResponses Map 的 computed 属性实现，不走API调用。
 * 核心联动链：D7-2→D7-1(按性质聚合) / D7-2→D7-1(按账龄聚合, segment-driven)
 *            / D7-3→D7-1(调整分录按性质/账龄双分组) / D7-7→D7-2(期后结转) / D7-1→附注
 *
 * Spec: .kiro/specs/d7-contract-liabilities-enhancement/
 * Task: 4
 * Requirements: 4.1, 4.2, 4.3, 4.4, 10.1, 10.2
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import {
  aggregateByNature,
  aggregateAgingByKeys,
  collectAgingKeys,
  calcSubtotal,
  parseNum,
  type DetailRow,
} from './useD7FormulaEngine'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from './useD7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD7CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /**
   * 项目账龄配置段（来自 useAgingConfig，subject='D7'，2-period）。
   * 提供时账龄聚合/长期筛选严格按项目配置段进行（THREE_YEAR/FIVE_YEAR/CUSTOM）；
   * 未提供时从明细数据收集段 key 兜底，避免固定 4 段导致取零。
   */
  segments?: Ref<AgingSegment[]>
}

/** 按性质聚合结果（4类 × prior/current） */
export interface NatureAggregationResult {
  revenue: { prior: number; current: number }       // 预收货款
  development: { prior: number; current: number }   // 开发项目预收款
  engineering: { prior: number; current: number }   // 预收工程款
  other: { prior: number; current: number }         // 其他
}

/** 调整合计（双分组：按性质 + 按账龄段） */
export interface AdjustmentTotals {
  byNature: Record<keyof NatureAggregationResult, { aje: number; rje: number }>
  byAging: Record<string, { aje: number; rje: number }>
  totalAje: number
  totalRje: number
}

/** 附注披露来源数据 */
export interface DisclosureSourceData {
  natureRows: Array<{ label: string; prior: number; current: number }>
  natureTotals: { prior: number; current: number }
  nonCurrentDeduction: { prior: number; current: number }
  contractLiabilityTotal: { prior: number; current: number }
}

/** ">1年" 段判定阈值（天）：dayFrom ≥ 366 视为账龄超过 1 年 */
const OVER_ONE_YEAR_DAY_FROM = 366

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseJsonArray(remark: string | null | undefined): any[] {
  if (!remark) return []
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function getRemark(map: Map<string, ChecklistResponse>, itemId: string): string | null {
  return map.get(itemId)?.remark ?? null
}

/** 性质类型映射：中文名→英文key */
const NATURE_TYPE_MAP: Record<string, keyof NatureAggregationResult> = {
  '预收货款': 'revenue',
  '开发项目预收款': 'development',
  '预收工程款': 'engineering',
  '其他': 'other',
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7CrossSheet(options: UseD7CrossSheetOptions) {
  const { allResponses, segments } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── 解析 D7-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<any[]>(() => safeParseJsonArray(getRemark(allResponses.value, 'D7-2-rows')))

  // ─── 有效账龄段（项目配置优先，数据兜底，最终 THREE_YEAR 默认） ──────────

  const agingSegments: ComputedRef<AgingSegment[]> = computed(() => {
    if (segments?.value?.length) return segments.value
    const dataKeys = collectAgingKeys(
      detailRows.value.map(r => ({
        agingPrior: (r.agingPrior ?? null) as Record<string, number> | null,
        agingAudited: (r.agingAudited ?? null) as Record<string, number> | null,
      })),
    )
    if (!dataKeys.length) return PRESET_SEGMENTS.THREE_YEAR
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

  // ─── D7-2 → D7-1 按性质聚合 ────────────────────────────────────────────

  const natureAggregation: ComputedRef<NatureAggregationResult> = computed(() => {
    const rows = detailRows.value
    const result: NatureAggregationResult = {
      revenue: { prior: 0, current: 0 },
      development: { prior: 0, current: 0 },
      engineering: { prior: 0, current: 0 },
      other: { prior: 0, current: 0 },
    }
    const currentAgg = aggregateByNature(rows as DetailRow[], 'endAudited')
    const priorAgg = aggregateByNature(rows as DetailRow[], 'priorAudited')
    for (const [chName, engKey] of Object.entries(NATURE_TYPE_MAP)) {
      result[engKey].current = currentAgg[chName] || 0
      result[engKey].prior = priorAgg[chName] || 0
    }
    return result
  })

  // ─── D7-2 → D7-1 按账龄聚合（segment-driven） ──────────────────────────

  /**
   * agingByKey: 按项目账龄配置段聚合期末审定(current)与期初审定(prior)，以段 key 为索引。
   * 支持 THREE_YEAR/FIVE_YEAR/CUSTOM 任意段数；行中不在配置段的旧段 key 被忽略。
   */
  const agingByKey: ComputedRef<{ current: Record<string, number>; prior: Record<string, number> }> = computed(() => {
    const rows = detailRows.value.map(r => ({
      agingPrior: (r.agingPrior ?? null) as Record<string, number> | null,
      agingAudited: (r.agingAudited ?? null) as Record<string, number> | null,
    }))
    return aggregateAgingByKeys(rows, agingSegmentKeys.value)
  })

  // ─── D7-3 → D7-1 调整分录按性质/账龄双分组 ──────────────────────────────

  /**
   * adjustmentTotals: 从 D7-3 调整分录行按性质(byNature)与账龄段(byAging)双分组累加。
   * entryType: debitAmount>0 → AJE，否则 creditAmount → RJE。
   * 未指定性质的行计入 other；未指定账龄段的行仅计入 total 不计入 byAging 明细。
   * 不变量：Σ byNature.aje === totalAje（每行必归入某性质）。
   *
   * Requirements: 10.1, 10.2
   */
  const adjustmentTotals: ComputedRef<AdjustmentTotals> = computed(() => {
    const byNature: AdjustmentTotals['byNature'] = {
      revenue: { aje: 0, rje: 0 },
      development: { aje: 0, rje: 0 },
      engineering: { aje: 0, rje: 0 },
      other: { aje: 0, rje: 0 },
    }
    const byAging: Record<string, { aje: number; rje: number }> = {}
    for (const key of agingSegmentKeys.value) byAging[key] = { aje: 0, rje: 0 }

    let totalAje = 0
    let totalRje = 0

    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-3-rows'))
    for (const r of rows) {
      const debit = parseNum(r.debitAmount)
      const credit = parseNum(r.creditAmount)
      const isAje = debit > 0
      const amount = isAje ? debit : credit
      if (amount === 0) continue

      const natureKey = NATURE_TYPE_MAP[r.natureType] ?? 'other'
      const band = typeof r.agingBand === 'string' ? r.agingBand : ''

      if (isAje) {
        byNature[natureKey].aje += amount
        totalAje += amount
        if (band && byAging[band]) byAging[band].aje += amount
      } else {
        byNature[natureKey].rje += amount
        totalRje += amount
        if (band && byAging[band]) byAging[band].rje += amount
      }
    }

    return { byNature, byAging, totalAje, totalRje }
  })

  // ─── D7-1 → 附注 审定表数据供附注引用 ──────────────────────────────────

  const adjudicationForDisclosure: ComputedRef<DisclosureSourceData> = computed(() => {
    const nat = natureAggregation.value
    const natureRows = [
      { label: '预收货款', prior: nat.revenue.prior, current: nat.revenue.current },
      { label: '开发项目预收款', prior: nat.development.prior, current: nat.development.current },
      { label: '预收工程款', prior: nat.engineering.prior, current: nat.engineering.current },
      { label: '其他', prior: nat.other.prior, current: nat.other.current },
    ]
    const natureTotals = {
      prior: nat.revenue.prior + nat.development.prior + nat.engineering.prior + nat.other.prior,
      current: nat.revenue.current + nat.development.current + nat.engineering.current + nat.other.current,
    }
    const map = allResponses.value
    const nonCurrentDeduction = {
      prior: parseNum(map.get('D7-1-adj-nature-non-current-deduction-priorAudited')?.remark),
      current: parseNum(map.get('D7-1-adj-nature-non-current-deduction-currentAudited')?.remark),
    }
    const contractLiabilityTotal = {
      prior: natureTotals.prior - nonCurrentDeduction.prior,
      current: natureTotals.current - nonCurrentDeduction.current,
    }
    return { natureRows, natureTotals, nonCurrentDeduction, contractLiabilityTotal }
  })

  // ─── D7-7 → D7-2 期后结转贷方合计 ─────────────────────────────────────

  const voucherPostTransferTotal: ComputedRef<number> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-7-post-rows'))
    return calcSubtotal(rows.map((r: any) => parseNum(r.creditAmount)))
  })

  // ─── 交叉验证：性质合计 vs 账龄合计（segment-driven） ───────────────────

  const crossValidation: ComputedRef<{ isConsistent: boolean; diff: number }> = computed(() => {
    const nat = natureAggregation.value
    const natureTotal = nat.revenue.current + nat.development.current +
      nat.engineering.current + nat.other.current

    const agingCur = agingByKey.value.current
    const agingTotal = Object.values(agingCur).reduce((s, v) => s + v, 0)

    const diff = natureTotal - agingTotal
    const isConsistent = Math.abs(diff) <= 0.01
    return { isConsistent, diff }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    natureAggregation,
    agingByKey,
    agingSegments,
    overOneYearKeys,
    adjustmentTotals,
    adjudicationForDisclosure,
    voucherPostTransferTotal,
    crossValidation,
    crossSheetStatus,
  }
}

export default useD7CrossSheet
