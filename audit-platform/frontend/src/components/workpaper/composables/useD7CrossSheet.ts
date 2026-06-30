/**
 * useD7CrossSheet — D7 合同负债跨Sheet联动 computed 响应式链
 *
 * 所有跨sheet数据流通过 allResponses Map 的 computed 属性实现，不走API调用。
 * 核心联动链：D7-2→D7-1(按性质聚合) / D7-2→D7-1(按账龄聚合) / D7-3→D7-1(AJE/RJE)
 *            / D7-7→D7-2(期后结转) / D7-1→附注
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 4.1
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 2.9, 24.3
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import {
  aggregateByNature,
  aggregateByAging,
  calcSubtotal,
  parseNum,
  type DetailRow,
  type AgingAggregation,
} from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD7CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

/** 按性质聚合结果（4类 × prior/current） */
export interface NatureAggregationResult {
  revenue: { prior: number; current: number }       // 预收货款
  development: { prior: number; current: number }   // 开发项目预收款
  engineering: { prior: number; current: number }   // 预收工程款
  other: { prior: number; current: number }         // 其他
}

/** 按账龄聚合结果（4段 × prior/current） */
export interface AgingAggregationResult {
  within1Year: { prior: number; current: number }
  year1to2: { prior: number; current: number }
  year2to3: { prior: number; current: number }
  over3Years: { prior: number; current: number }
}

/** 附注披露来源数据 */
export interface DisclosureSourceData {
  natureRows: Array<{ label: string; prior: number; current: number }>
  natureTotals: { prior: number; current: number }
  nonCurrentDeduction: { prior: number; current: number }
  contractLiabilityTotal: { prior: number; current: number }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 安全解析 JSON 数组（从 remark 字段），失败返回空数组 */
function safeParseJsonArray(remark: string | null | undefined): any[] {
  if (!remark) return []
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从 allResponses 中获取指定 item_id 的 remark */
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
  const { allResponses } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── D7-2 → D7-1 按性质聚合 ────────────────────────────────────────────

  /**
   * 从D7-2明细行按"款项性质(natureType)"聚合期末审定数(endAudited)和期初审定数(priorAudited)
   * 填入审定表D7-1"按性质分类"区块4行。
   *
   * Requirements: 3.1
   */
  const natureAggregation: ComputedRef<NatureAggregationResult> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-2-rows'))

    // 初始化结果
    const result: NatureAggregationResult = {
      revenue: { prior: 0, current: 0 },
      development: { prior: 0, current: 0 },
      engineering: { prior: 0, current: 0 },
      other: { prior: 0, current: 0 },
    }

    // 使用 aggregateByNature 按 endAudited 聚合（期末审定）
    const currentAgg = aggregateByNature(rows as DetailRow[], 'endAudited')
    // 按 priorAudited 聚合（期初审定）
    const priorAgg = aggregateByNature(rows as DetailRow[], 'priorAudited')

    // 映射到标准4类
    for (const [chName, engKey] of Object.entries(NATURE_TYPE_MAP)) {
      result[engKey].current = currentAgg[chName] || 0
      result[engKey].prior = priorAgg[chName] || 0
    }

    return result
  })

  // ─── D7-2 → D7-1 按账龄聚合 ────────────────────────────────────────────

  /**
   * 从D7-2明细行按审定账龄4段列SUM，填入审定表D7-1"按账龄分类"区块4行。
   * 同时对prior期间的priorAging1~4做聚合。
   *
   * Requirements: 3.2
   */
  const agingAggregation: ComputedRef<AgingAggregationResult> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-2-rows'))

    // 期末账龄聚合（endAging1~4）
    const currentAging = aggregateByAging(rows as DetailRow[])

    // 期初账龄聚合（priorAging1~4）
    let priorWithin1Year = 0
    let priorYear1to2 = 0
    let priorYear2to3 = 0
    let priorOver3Years = 0
    for (const row of rows) {
      priorWithin1Year += parseNum(row.priorAging1)
      priorYear1to2 += parseNum(row.priorAging2)
      priorYear2to3 += parseNum(row.priorAging3)
      priorOver3Years += parseNum(row.priorAging4)
    }

    return {
      within1Year: { prior: priorWithin1Year, current: currentAging.within1Year },
      year1to2: { prior: priorYear1to2, current: currentAging.year1to2 },
      year2to3: { prior: priorYear2to3, current: currentAging.year2to3 },
      over3Years: { prior: priorOver3Years, current: currentAging.over3Years },
    }
  })

  // ─── D7-3 → D7-1 AJE/RJE合计 ──────────────────────────────────────────

  /**
   * 从D7-3调整分录行汇总AJE（借方合计）和RJE（贷方合计）。
   *
   * Requirements: 3.5
   */
  const adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-3-rows'))

    const ajeTotal = calcSubtotal(rows.map((r: any) => parseNum(r.debitAmount)))
    const rjeTotal = calcSubtotal(rows.map((r: any) => parseNum(r.creditAmount)))

    return { ajeTotal, rjeTotal }
  })

  // ─── D7-1 → 附注 审定表数据供附注引用 ──────────────────────────────────

  /**
   * 提供审定表已聚合数据供附注披露组件引用。
   * 包含按性质分类4行+小计+非流动负债扣减+合同负债合计（prior/current）。
   *
   * Requirements: 3.4
   */
  const adjudicationForDisclosure: ComputedRef<DisclosureSourceData> = computed(() => {
    const nat = natureAggregation.value

    // 4类行数据
    const natureRows = [
      { label: '预收货款', prior: nat.revenue.prior, current: nat.revenue.current },
      { label: '开发项目预收款', prior: nat.development.prior, current: nat.development.current },
      { label: '预收工程款', prior: nat.engineering.prior, current: nat.engineering.current },
      { label: '其他', prior: nat.other.prior, current: nat.other.current },
    ]

    // 小计
    const natureTotals = {
      prior: nat.revenue.prior + nat.development.prior + nat.engineering.prior + nat.other.prior,
      current: nat.revenue.current + nat.development.current + nat.engineering.current + nat.other.current,
    }

    // 非流动负债扣减（从allResponses读取手动编辑值）
    const map = allResponses.value
    const nonCurrentDeduction = {
      prior: parseNum(map.get('D7-1-adj-nature-non-current-deduction-priorAudited')?.remark),
      current: parseNum(map.get('D7-1-adj-nature-non-current-deduction-currentAudited')?.remark),
    }

    // 合同负债合计 = 小计 - 非流动负债扣减
    const contractLiabilityTotal = {
      prior: natureTotals.prior - nonCurrentDeduction.prior,
      current: natureTotals.current - nonCurrentDeduction.current,
    }

    return { natureRows, natureTotals, nonCurrentDeduction, contractLiabilityTotal }
  })

  // ─── D7-7 → D7-2 期后结转贷方合计 ─────────────────────────────────────

  /**
   * D7-7凭证检查"期后结转"区块的贷方金额合计，
   * 供D7-2明细表"期后结转"列交叉验证。
   *
   * Requirements: 24.3
   */
  const voucherPostTransferTotal: ComputedRef<number> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D7-7-post-rows'))
    return calcSubtotal(rows.map((r: any) => parseNum(r.creditAmount)))
  })

  // ─── 交叉验证：性质合计 vs 账龄合计 ────────────────────────────────────

  /**
   * 双区块交叉验证：按性质分类的期末审定合计 应等于 按账龄分类的期末审定合计。
   * 当每行的 endAging1+endAging2+endAging3+endAging4 === endAudited 时恒成立。
   *
   * Requirements: 2.9
   */
  const crossValidation: ComputedRef<{ isConsistent: boolean; diff: number }> = computed(() => {
    const nat = natureAggregation.value
    const aging = agingAggregation.value

    // 按性质聚合的期末合计
    const natureTotal = nat.revenue.current + nat.development.current +
      nat.engineering.current + nat.other.current

    // 按账龄聚合的期末合计
    const agingTotal = aging.within1Year.current + aging.year1to2.current +
      aging.year2to3.current + aging.over3Years.current

    const diff = natureTotal - agingTotal
    const isConsistent = Math.abs(diff) <= 0.01

    return { isConsistent, diff }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    natureAggregation,
    agingAggregation,
    adjustmentTotals,
    adjudicationForDisclosure,
    voucherPostTransferTotal,
    crossValidation,
    crossSheetStatus,
  }
}

export default useD7CrossSheet
