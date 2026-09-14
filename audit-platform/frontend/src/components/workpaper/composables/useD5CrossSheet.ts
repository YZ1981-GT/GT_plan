/**
 * useD5CrossSheet — D5 应收款项融资跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('D5-2-rows')?.remark 存 JSON 数组，try/catch 解析。
 *
 * 跨Sheet映射：
 * - D5-2 → D5-1：按类别（应收票据/应收账款）聚合 endAudited / priorAudited
 * - D5-4 → D5-1：OCI变动 = 小计 - D5-4公允价值合计
 * - D5-3 → D5-1：AJE/RJE汇总
 * - D5-1 → 附注：审定表数据供附注引用
 * - D5-4 合计行：票面合计/公允价值合计
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 4.1
 * Requirements: 3.1, 3.2, 3.5, 8.3
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { parseNum } from './useD5FormulaEngine'
import type { ChecklistResponse } from './useD5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD5CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

/** D5-2 明细行原始 JSON 结构（remark 中存储） */
export interface D5DetailRowRaw {
  rowId: string
  category: string            // 类别（应收票据/应收账款）
  itemName?: string
  priorUnadjusted?: number
  priorAje?: number
  priorRje?: number
  priorAudited?: number       // F: =C+D+E
  periodIncrease?: number
  periodDecrease?: number
  endBalance?: number
  entityReclass?: number
  endUnadjusted?: number
  endAje?: number
  endRje?: number
  endAudited?: number         // O: =L+M+N
  endOciImpairment?: number
  remark?: string
}

/** D5-3 调整分录行原始 JSON 结构 */
export interface D5AdjustmentRowRaw {
  rowId: string
  description?: string
  category?: string           // 报表调整/账项调整
  reportItem?: string
  accountName?: string
  noteItem?: string
  placeholder?: string
  debitAmount?: number
  creditAmount?: number
  indexRef?: string
  remark?: string
}

/** D5-4 公允价值测算行原始 JSON 结构 */
export interface D5FairValueRowRaw {
  rowId: string
  category?: string
  itemName?: string
  billNo?: string
  faceValue?: number          // D: 票面金额
  measurementDate?: string
  maturityDate?: string
  remainingDays?: number
  discountRate?: number
  discountInterest?: number
  discountAmount?: number
  fairValue?: number          // K: 期末公允价值
  fvHierarchy?: string
  remark?: string
}

/** D5附注披露数据结构 */
export interface D5DisclosureSourceData {
  /** 应收票据审定数 */
  notesReceivable: { prior: number; current: number }
  /** 应收账款审定数 */
  accountsReceivable: { prior: number; current: number }
  /** 小计 */
  subtotal: { prior: number; current: number }
  /** OCI变动 */
  ociChange: { prior: number; current: number }
  /** 公允价值合计 */
  fairValueTotal: { prior: number; current: number }
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

export function useD5CrossSheet(options: UseD5CrossSheetOptions) {
  const { allResponses } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── 解析 D5-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<D5DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('D5-2-rows')
    return safeParseRows<D5DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 D5-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<D5AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('D5-3-rows')
    return safeParseRows<D5AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 D5-4 公允价值测算行数据 ──────────────────────────────────────

  const fairValueRows = computed<D5FairValueRowRaw[]>(() => {
    const resp = allResponses.value.get('D5-4-rows')
    return safeParseRows<D5FairValueRowRaw>(resp?.remark)
  })

  // ─── D5-2 → D5-1 按类别聚合（Requirement 3.1）──────────────────────────

  /**
   * categoryAggregation: 按类别分组，聚合 endAudited 和 priorAudited
   * - 类别=应收票据 → notesReceivable
   * - 类别=应收账款 → accountsReceivable
   */
  const categoryAggregation: ComputedRef<{
    notesReceivable: { prior: number; current: number }
    accountsReceivable: { prior: number; current: number }
  }> = computed(() => {
    let notesPrior = 0
    let notesCurrent = 0
    let accountsPrior = 0
    let accountsCurrent = 0

    for (const row of detailRows.value) {
      const endAudited = parseNum(row.endAudited)
      const priorAudited = parseNum(row.priorAudited)

      if (row.category === '应收票据') {
        notesCurrent += endAudited
        notesPrior += priorAudited
      } else if (row.category === '应收账款') {
        accountsCurrent += endAudited
        accountsPrior += priorAudited
      }
    }

    return {
      notesReceivable: { prior: notesPrior, current: notesCurrent },
      accountsReceivable: { prior: accountsPrior, current: accountsCurrent },
    }
  })

  // ─── D5-4 公允价值合计（Requirement 3.2 前置）──────────────────────────

  /**
   * fairValueTotal: D5-4 所有行的 fairValue 汇总
   * 期末: SUM(所有行的 fairValue)
   * 期初: 暂取0（D5-4通常只测算期末，期初参考上年底稿）
   */
  const fairValueTotal: ComputedRef<{ prior: number; current: number }> = computed(() => {
    let currentTotal = 0
    let priorTotal = 0

    for (const row of fairValueRows.value) {
      currentTotal += parseNum(row.fairValue)
    }

    // 期初公允价值合计：从 allResponses 获取上期存储值
    const priorResp = allResponses.value.get('D5-4-prior-fv-total')
    priorTotal = parseNum(priorResp?.remark)

    return { prior: priorTotal, current: currentTotal }
  })

  // ─── D5-4 → D5-1 OCI变动（Requirement 3.2）────────────────────────────

  /**
   * ociChange: OCI公允价值变动 = 小计（票面） - D5-4公允价值合计
   *
   * 审定表特殊结构：公允价值合计 = 小计 - OCI变动
   * 即 OCI变动 = 小计 - 公允价值合计
   *
   * 小计 = 应收票据审定 + 应收账款审定（categoryAggregation合计）
   */
  const ociChange: ComputedRef<{ prior: number; current: number }> = computed(() => {
    const agg = categoryAggregation.value
    const fv = fairValueTotal.value

    const subtotalCurrent = agg.notesReceivable.current + agg.accountsReceivable.current
    const subtotalPrior = agg.notesReceivable.prior + agg.accountsReceivable.prior

    return {
      prior: subtotalPrior - fv.prior,
      current: subtotalCurrent - fv.current,
    }
  })

  // ─── D5-3 → D5-1 AJE/RJE 汇总（Requirement 3.5）──────────────────────

  /**
   * adjustmentTotals: 从D5-3行汇总 AJE/RJE 金额
   * - category='账项调整' → 借方金额累加为 ajeTotal
   * - category='重分类调整' 或 '报表调整' → 借方金额累加为 rjeTotal
   *
   * 简化模型：借方金额=增加审定数（debitAmount）
   */
  const adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }> = computed(() => {
    let ajeTotal = 0
    let rjeTotal = 0

    for (const row of adjustmentRows.value) {
      const debit = parseNum(row.debitAmount)
      const credit = parseNum(row.creditAmount)
      // 净额 = 借方 - 贷方（借方科目：借方增加审定数，贷方减少审定数）
      const netAmount = debit - credit

      if (row.category === '账项调整') {
        ajeTotal += netAmount
      } else if (row.category === '报表调整' || row.category === '重分类调整') {
        rjeTotal += netAmount
      }
    }

    return { ajeTotal, rjeTotal }
  })

  // ─── D5-1 → 附注 审定表数据供附注引用（Requirement 8.3）──────────────

  /**
   * adjudicationForDisclosure: 审定表数据供附注披露引用
   * 组合 categoryAggregation + ociChange + fairValueTotal
   */
  const adjudicationForDisclosure: ComputedRef<D5DisclosureSourceData> = computed(() => {
    const agg = categoryAggregation.value
    const oci = ociChange.value
    const fv = fairValueTotal.value

    const subtotalPrior = agg.notesReceivable.prior + agg.accountsReceivable.prior
    const subtotalCurrent = agg.notesReceivable.current + agg.accountsReceivable.current

    return {
      notesReceivable: agg.notesReceivable,
      accountsReceivable: agg.accountsReceivable,
      subtotal: { prior: subtotalPrior, current: subtotalCurrent },
      ociChange: oci,
      fairValueTotal: fv,
    }
  })

  // ─── D5 vs D1 跨底稿勾稽提示 ────────────────────────────────────────

  /**
   * D5审定合计 + D1应收票据审定 应≈ TB(1121+1124)
   * 本 computed 仅提供 D5 侧数据，D1 侧需主入口从外部注入
   */
  const d5AuditedTotal: ComputedRef<number> = computed(() => {
    const agg = categoryAggregation.value
    return agg.notesReceivable.current + agg.accountsReceivable.current
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // D5-2 → D5-1 按类别聚合
    categoryAggregation,
    // D5-4 → D5-1 OCI变动
    ociChange,
    // D5-3 → D5-1 AJE/RJE
    adjustmentTotals,
    // D5-1 → 附注
    adjudicationForDisclosure,
    // D5-4 公允价值合计
    fairValueTotal,
    // D5 vs D1 跨底稿勾稽
    d5AuditedTotal,
    // 状态
    crossSheetStatus,
  }
}

export default useD5CrossSheet
