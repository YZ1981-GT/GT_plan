/**
 * useD4CrossSheet — D4 营业收入跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('D4-X-rows')?.remark 存 JSON 数组，try/catch 解析。
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 4.1
 * Requirements: 17.1-17.9, 14.1
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { D4_MAIN_REVENUE_STANDARD, D4_OTHER_REVENUE_STANDARD } from './d4AccountScope'
import {
  calcMonthlyTotal,
  calcAuditedWithAdj,
  calcSubtotal,
  calcProportion,
  isIpoGroupVisible,
  parseNum,
} from './useD4FormulaEngine'
import type { ChecklistResponse, ProjectContext } from './useD4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD4CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectContext: Ref<ProjectContext>
}

/** D4-2 行原始 JSON 结构（remark 中存储） */
interface D4Row2Raw {
  rowId: string
  product: string
  months: number[]
  auditAdjustment?: number
  priorUnadjusted?: number
  priorAdjustment?: number
  remark?: string
}

/** D4-3 行原始 JSON 结构 */
interface D4Row3Raw {
  rowId: string
  item: string
  currentUnadjusted?: number
  currentAdjustment?: number
  currentAudited?: number
  priorUnadjusted?: number
  priorAdjustment?: number
  priorAudited?: number
}

/** D4-4 行原始 JSON 结构 */
interface D4Row4Raw {
  rowId: string
  accountCode?: string
  accountName?: string
  entryType?: 'AJE' | 'RJE'
  debitAmount?: number
  creditAmount?: number
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

export function useD4CrossSheet(options: UseD4CrossSheetOptions) {
  const { allResponses, projectContext } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── D4-2 → D4-1 按产品聚合 ───────────────────────────────────────────

  /** 解析 D4-2 行数据 */
  const d4Row2Data = computed<D4Row2Raw[]>(() => {
    const resp = allResponses.value.get('D4-2-rows')
    return safeParseRows<D4Row2Raw>(resp?.remark)
  })

  /**
   * 按产品聚合：每个产品的本期审定 = SUM(months) + auditAdjustment
   * 上期审定 = priorUnadjusted + priorAdjustment
   */
  const mainRevenueByProduct: ComputedRef<Record<string, { current: number; prior: number }>> = computed(() => {
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of d4Row2Data.value) {
      const product = row.product || '未命名'
      const monthsArr = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = calcMonthlyTotal(monthsArr)
      const audited = calcAuditedWithAdj(periodTotal, parseNum(row.auditAdjustment))
      const priorAudited = calcAuditedWithAdj(parseNum(row.priorUnadjusted), parseNum(row.priorAdjustment))

      if (!result[product]) {
        result[product] = { current: 0, prior: 0 }
      }
      result[product].current += audited
      result[product].prior += priorAudited
    }
    return result
  })

  /** 主营合计 = 所有产品 current/prior 之和 */
  const mainRevenueTotal: ComputedRef<{ current: number; prior: number }> = computed(() => {
    const byProduct = mainRevenueByProduct.value
    const products = Object.values(byProduct)
    return {
      current: calcSubtotal(products.map(p => p.current)),
      prior: calcSubtotal(products.map(p => p.prior)),
    }
  })

  // ─── D4-3 → D4-1 按项目聚合 ───────────────────────────────────────────

  /** 解析 D4-3 行数据 */
  const d4Row3Data = computed<D4Row3Raw[]>(() => {
    const resp = allResponses.value.get('D4-3-rows')
    return safeParseRows<D4Row3Raw>(resp?.remark)
  })

  /**
   * 按项目聚合：每个项目的 currentAudited / priorAudited
   */
  const otherRevenueByItem: ComputedRef<Record<string, { current: number; prior: number }>> = computed(() => {
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of d4Row3Data.value) {
      const item = row.item || '未命名'
      const currentAudited = row.currentAudited != null
        ? parseNum(row.currentAudited)
        : calcAuditedWithAdj(parseNum(row.currentUnadjusted), parseNum(row.currentAdjustment))
      const priorAudited = row.priorAudited != null
        ? parseNum(row.priorAudited)
        : calcAuditedWithAdj(parseNum(row.priorUnadjusted), parseNum(row.priorAdjustment))

      if (!result[item]) {
        result[item] = { current: 0, prior: 0 }
      }
      result[item].current += currentAudited
      result[item].prior += priorAudited
    }
    return result
  })

  /** 其他合计 = 所有项目 current/prior 之和 */
  const otherRevenueTotal: ComputedRef<{ current: number; prior: number }> = computed(() => {
    const byItem = otherRevenueByItem.value
    const items = Object.values(byItem)
    return {
      current: calcSubtotal(items.map(i => i.current)),
      prior: calcSubtotal(items.map(i => i.prior)),
    }
  })

  // ─── D4-4 → D4-1 AJE/RJE ─────────────────────────────────────────────

  /** 解析 D4-4 行数据 */
  const d4Row4Data = computed<D4Row4Raw[]>(() => {
    const resp = allResponses.value.get('D4-4-rows')
    return safeParseRows<D4Row4Raw>(resp?.remark)
  })

  /**
   * 按科目+类型分拆 AJE/RJE 合计
   * 6001 → 主营；6051 → 其他
   * 金额 = debit - credit（损益类贷方科目：借增贷减）
   */
  const adjustmentTotals: ComputedRef<{ mainAje: number; mainRje: number; otherAje: number; otherRje: number }> = computed(() => {
    let mainAje = 0
    let mainRje = 0
    let otherAje = 0
    let otherRje = 0

    for (const row of d4Row4Data.value) {
      const code = row.accountCode || row.accountName || ''
      const amount = parseNum(row.debitAmount) - parseNum(row.creditAmount)
      const isMain = code.includes(D4_MAIN_REVENUE_STANDARD)
      const isOther = code.includes(D4_OTHER_REVENUE_STANDARD)
      const isAje = row.entryType === 'AJE'

      if (isMain) {
        if (isAje) mainAje += amount
        else mainRje += amount
      } else if (isOther) {
        if (isAje) otherAje += amount
        else otherRje += amount
      }
    }

    return { mainAje, mainRje, otherAje, otherRje }
  })

  // ─── D4-2 → D4-8 产品毛利数据 ────────────────────────────────────────

  /** 产品收入列表（供 D4-8 消费） */
  const productRevenueForMargin: ComputedRef<Array<{ product: string; revenue: number; priorRevenue: number }>> = computed(() => {
    const byProduct = mainRevenueByProduct.value
    return Object.entries(byProduct).map(([product, vals]) => ({
      product,
      revenue: vals.current,
      priorRevenue: vals.prior,
    }))
  })

  // ─── D4-2 → D4-9 客户结构数据（Top排名） ─────────────────────────────

  /** 按审定金额降序排列，计算占比 */
  const customerStructureData: ComputedRef<Array<{ name: string; amount: number; proportion: number }>> = computed(() => {
    const rows = d4Row2Data.value
    if (rows.length === 0) return []

    // 计算每行审定金额
    const rowsWithAudited = rows.map(row => {
      const monthsArr = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = calcMonthlyTotal(monthsArr)
      const audited = calcAuditedWithAdj(periodTotal, parseNum(row.auditAdjustment))
      return { name: row.product || '未命名', amount: audited }
    })

    // 按金额降序排列
    const sorted = [...rowsWithAudited].sort((a, b) => b.amount - a.amount)

    // 计算总额和占比
    const total = calcSubtotal(sorted.map(r => r.amount))
    return sorted.map(row => ({
      name: row.name,
      amount: row.amount,
      proportion: calcProportion(row.amount, total),
    }))
  })

  // ─── D4-1 → 附注 ─────────────────────────────────────────────────────

  /** 审定合计数据供附注使用 */
  const adjudicationForDisclosure: ComputedRef<{ mainAudited: number; otherAudited: number; total: number }> = computed(() => {
    const main = mainRevenueTotal.value.current
    const other = otherRevenueTotal.value.current
    return {
      mainAudited: main,
      otherAudited: other,
      total: main + other,
    }
  })

  // ─── IPO组可见性 ──────────────────────────────────────────────────────

  /** 根据 business_category 判断 IPO/舞弊组一级Tab可见性 */
  const ipoGroupVisible: ComputedRef<boolean> = computed(() => {
    return isIpoGroupVisible(projectContext.value.business_category || '')
  })

  // ─── D4-2/D4-3行结构→D4-1行同步（CustomEvent） ────────────────────

  /**
   * 同步产品行到审定表
   * D4-2 addRow 时→D4-1 主营区块新增对应行（isFromCrossSheet=true）
   * D4-2 removeRow 时→D4-1 同步删除
   */
  function syncProductRowToAdjudication(action: 'add' | 'remove', product: string): void {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('d4:sync-row', {
      detail: { section: 'main-revenue', action, product },
    }))
  }

  /**
   * 同步其他项目行到审定表
   * D4-3 addRow 时→D4-1 其他区块新增对应行
   * D4-3 removeRow 时→D4-1 同步删除
   */
  function syncOtherItemRowToAdjudication(action: 'add' | 'remove', item: string): void {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('d4:sync-row', {
      detail: { section: 'other-revenue', action, item },
    }))
  }

  // ─── 附注成本跨循环取数（从TB科目6401+6402） ────────────────────────

  /**
   * 从 allResponses 中读取成本数据
   * D4TabDisclosureListed.vue 使用 item_id: D4-note-listed-cost-6401 / D4-note-listed-cost-6402
   * 这些值由 TB resolver 填入，或由 M 循环审定后回写
   */
  const costFromTb: ComputedRef<{ mainCost: number; otherCost: number; priorMainCost: number; priorOtherCost: number }> = computed(() => {
    const cost6401 = allResponses.value.get('D4-note-listed-cost-6401')
    const cost6402 = allResponses.value.get('D4-note-listed-cost-6402')

    // remark 存 JSON: { current: number, prior: number }
    let mainCost = 0
    let priorMainCost = 0
    let otherCost = 0
    let priorOtherCost = 0

    if (cost6401?.remark) {
      try {
        const data = JSON.parse(cost6401.remark)
        mainCost = parseNum(data.current)
        priorMainCost = parseNum(data.prior)
      } catch { /* fallback 0 */ }
    }

    if (cost6402?.remark) {
      try {
        const data = JSON.parse(cost6402.remark)
        otherCost = parseNum(data.current)
        priorOtherCost = parseNum(data.prior)
      } catch { /* fallback 0 */ }
    }

    return { mainCost, otherCost, priorMainCost, priorOtherCost }
  })

  // ─── 出口/境外适用性 ──────────────────────────────────────────────────

  /** 项目是否有出口业务（控制 D4-16/D4-26 Tab 可见性） */
  const hasExportBusiness: ComputedRef<boolean> = computed(() => {
    return !!projectContext.value.has_export_business
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // D4-2 → D4-1 按产品聚合
    mainRevenueByProduct,
    mainRevenueTotal,
    // D4-3 → D4-1 按项目聚合
    otherRevenueByItem,
    otherRevenueTotal,
    // D4-4 → D4-1 AJE/RJE
    adjustmentTotals,
    // D4-2 → D4-8 产品毛利数据
    productRevenueForMargin,
    // D4-2 → D4-9 客户结构数据（Top排名）
    customerStructureData,
    // D4-1 → 附注
    adjudicationForDisclosure,
    // IPO组可见性
    ipoGroupVisible,
    // D4-2/D4-3行结构→D4-1行同步
    syncProductRowToAdjudication,
    syncOtherItemRowToAdjudication,
    // 附注成本跨循环取数
    costFromTb,
    // 出口/境外适用性
    hasExportBusiness,
    // 状态
    crossSheetStatus,
  }
}

export default useD4CrossSheet
