/**
 * useF5CrossSheet — F5 营业成本跨底稿勾稽引擎
 *
 * 核心职责：
 * 1. 毛利率分析：F5审定 vs D4营业收入审定 → 综合毛利率 + 产品级毛利率
 * 2. 成本收入比：F5审定/D4审定
 * 3. F5-1↔F5-2↔F5-7 内部勾稽一致性
 * 4. 全局告警输出(供主入口el-alert消费)
 *
 * 数据来源：
 * - F5-1: allResponses 中 MAIN/OTHER 存储键 → 审定合计
 * - D4-1: 跨底稿从 D4 checklist-responses 拉取 (optional pull)
 * - F5-7: allResponses 中 F5-7-cost-rollforward 存储键 → 倒轧结果行
 * - TB: project_context.tb_amount (render策略注入)
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcGrossMargin, calcChangeRate } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface UseF5CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectId: Ref<string>
  projectContext?: Ref<Record<string, any>>
  adjudicatedCOGS?: Ref<number>
}

export interface F5GlobalAlert {
  type: 'warning' | 'error' | 'info'
  message: string
  /** 排除的 sheetName（在该 sheet 内不显示此告警） */
  excludeSheets?: string[]
}

export interface F5GrossProfitAnalysis {
  revenue: number
  cost: number
  grossProfit: number
  grossMargin: number | 'N/A'
  priorRevenue: number
  priorCost: number
  priorGrossProfit: number
  priorGrossMargin: number | 'N/A'
  marginChange: number | 'N/A'
}

// ─── 常量 ────────────────────────────────────────────────────────────────────
const MAIN_STORAGE_KEY = 'F5-1-adj-main-rows'
const OTHER_STORAGE_KEY = 'F5-1-adj-other-rows'
const TB_STORAGE_KEY = 'F5-1-adj-tb-6401'
const MONTHLY_ROWS_KEY = 'F5-2-monthly-rows'
const ROLLFORWARD_KEY = 'F5-7-cost-rollforward'

/** D4 审定数据的 item_id（D4-1 主营未审存储） */
const D4_MAIN_STORAGE_KEY = 'D4-1-adj-main-rows'
const D4_TB_KEY = 'D4-1-adj-tb-6001'

/** 毛利率变动阈值(百分点)，超过则告警 */
const MARGIN_CHANGE_THRESHOLD = 5

// ─── 辅助函数 ────────────────────────────────────────────────────────────────

function sumAdjusted(jsonStr: string | null | undefined): number {
  if (!jsonStr) return 0
  try {
    const rows = JSON.parse(jsonStr)
    if (!Array.isArray(rows)) return 0
    return rows.reduce((acc: number, r: any) => {
      const adj = parseNum(r.currentUnadjusted) + parseNum(r.currentAje) + parseNum(r.currentRje)
      return acc + adj
    }, 0)
  } catch { return 0 }
}

function sumPriorAdjusted(jsonStr: string | null | undefined): number {
  if (!jsonStr) return 0
  try {
    const rows = JSON.parse(jsonStr)
    if (!Array.isArray(rows)) return 0
    return rows.reduce((acc: number, r: any) => {
      const adj = parseNum(r.priorUnadjusted) + parseNum(r.priorAje) + parseNum(r.priorRje)
      return acc + adj
    }, 0)
  } catch { return 0 }
}

function sumMonthlyCurrentUnaudited(jsonStr: string | null | undefined): number {
  if (!jsonStr) return 0
  try {
    const rows = JSON.parse(jsonStr)
    if (!Array.isArray(rows)) return 0
    return rows.reduce((acc: number, r: any) => {
      if (Array.isArray(r.months)) {
        return acc + r.months.reduce((s: number, m: any) => s + parseNum(m), 0)
      }
      return acc + parseNum(r.currentUnaudited ?? r.currentUnadjusted ?? r.yearTotal)
    }, 0)
  } catch { return 0 }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF5CrossSheet(options: UseF5CrossSheetOptions) {
  const { allResponses, projectId, projectContext, adjudicatedCOGS } = options

  // D4 数据（跨底稿拉取，可选）
  const d4Revenue = ref<number>(0)
  const d4PriorRevenue = ref<number>(0)
  const d4Loaded = ref(false)

  // ─── F5 审定数汇总 ─────────────────────────────────────────────────
  const f5MainAdjusted = computed(() =>
    sumAdjusted(allResponses.value.get(MAIN_STORAGE_KEY)?.remark),
  )
  const f5OtherAdjusted = computed(() =>
    sumAdjusted(allResponses.value.get(OTHER_STORAGE_KEY)?.remark),
  )
  const f5TotalAdjusted = computed(() => f5MainAdjusted.value + f5OtherAdjusted.value)

  const f5MainPriorAdjusted = computed(() =>
    sumPriorAdjusted(allResponses.value.get(MAIN_STORAGE_KEY)?.remark),
  )
  const f5OtherPriorAdjusted = computed(() =>
    sumPriorAdjusted(allResponses.value.get(OTHER_STORAGE_KEY)?.remark),
  )
  const f5TotalPriorAdjusted = computed(() => f5MainPriorAdjusted.value + f5OtherPriorAdjusted.value)

  // ─── TB 核对 ───────────────────────────────────────────────────────
  const tbAmount = computed(() => {
    // 优先从 project_context（后端 render 注入）
    if (projectContext?.value?.tb_amount) return parseNum(projectContext.value.tb_amount)
    return parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark)
  })

  const tbVariance = computed(() =>
    Math.round((f5TotalAdjusted.value - tbAmount.value) * 100) / 100,
  )

  // ─── 毛利率分析 ────────────────────────────────────────────────────
  const grossProfitAnalysis: ComputedRef<F5GrossProfitAnalysis> = computed(() => {
    const revenue = d4Revenue.value
    const cost = f5TotalAdjusted.value
    const grossProfit = revenue - cost
    const grossMargin = calcGrossMargin(revenue, cost)

    const priorRevenue = d4PriorRevenue.value
    const priorCost = f5TotalPriorAdjusted.value
    const priorGrossProfit = priorRevenue - priorCost
    const priorGrossMargin = calcGrossMargin(priorRevenue, priorCost)

    const marginChange = (typeof grossMargin === 'number' && typeof priorGrossMargin === 'number')
      ? grossMargin - priorGrossMargin
      : 'N/A'

    return {
      revenue, cost, grossProfit, grossMargin,
      priorRevenue, priorCost, priorGrossProfit, priorGrossMargin,
      marginChange,
    }
  })

  // ─── F5-2月度合计 ↔ F5-1 主营未审 勾稽 ─────────────────────────────
  const monthlyTotal = computed(() =>
    sumMonthlyCurrentUnaudited(
      allResponses.value.get(MONTHLY_ROWS_KEY)?.remark
        ?? allResponses.value.get('F5-2-rows')?.remark,
    ),
  )

  const f5MainUnadjusted = computed(() => {
    const json = allResponses.value.get(MAIN_STORAGE_KEY)?.remark
    if (!json) return 0
    try {
      const rows = JSON.parse(json)
      if (!Array.isArray(rows)) return 0
      return rows.reduce((acc: number, r: any) => acc + parseNum(r.currentUnadjusted), 0)
    } catch { return 0 }
  })

  const monthlyVsAdjudicationDiff = computed(() =>
    Math.round((monthlyTotal.value - f5MainUnadjusted.value) * 100) / 100,
  )

  // ─── F5-7 倒轧终行 ↔ F5-1 审定合计 ─────────────────────────────────
  const rollforwardCOGS = computed(() => {
    if (adjudicatedCOGS?.value) return adjudicatedCOGS.value
    const json = allResponses.value.get(ROLLFORWARD_KEY)?.remark
    if (!json) return 0
    try {
      const stored = JSON.parse(json)
      if (typeof stored === 'object' && !Array.isArray(stored)) {
        // 存储格式 {rowKey: {unadjusted, aje, ...}}
        const cogsRow = stored['mainBusinessCOGS'] ?? stored['cogs']
        if (cogsRow) return parseNum(cogsRow.unadjusted) + parseNum(cogsRow.aje)
      }
      return 0
    } catch { return 0 }
  })

  const rollforwardVsAdjudicationDiff = computed(() =>
    Math.round((rollforwardCOGS.value - f5TotalAdjusted.value) * 100) / 100,
  )

  // ─── 全局告警 ──────────────────────────────────────────────────────
  const globalAlerts: ComputedRef<F5GlobalAlert[]> = computed(() => {
    const alerts: F5GlobalAlert[] = []

    // 1. F5-1 ↔ TB 差异
    if (tbAmount.value > 0 && Math.abs(tbVariance.value) > 1) {
      alerts.push({
        type: 'warning',
        message: `F5-1审定合计(${f5TotalAdjusted.value.toLocaleString('zh-CN')}) ↔ TB 6401(${tbAmount.value.toLocaleString('zh-CN')}) 差异 ${tbVariance.value.toLocaleString('zh-CN')} 元`,
        excludeSheets: ['F5-1'],
      })
    }

    // 2. F5-7 倒轧 ↔ F5-1 审定
    if (rollforwardCOGS.value > 0 && Math.abs(rollforwardVsAdjudicationDiff.value) > 1) {
      alerts.push({
        type: 'error',
        message: `F5-7成本倒轧(${rollforwardCOGS.value.toLocaleString('zh-CN')}) ↔ F5-1审定合计(${f5TotalAdjusted.value.toLocaleString('zh-CN')}) 差异 ${rollforwardVsAdjudicationDiff.value.toLocaleString('zh-CN')} 元`,
        excludeSheets: ['F5-7'],
      })
    }

    // 3. 毛利率异常（需D4已加载）
    if (d4Loaded.value) {
      const gpa = grossProfitAnalysis.value
      if (typeof gpa.marginChange === 'number' && Math.abs(gpa.marginChange) > MARGIN_CHANGE_THRESHOLD) {
        const direction = gpa.marginChange > 0 ? '上升' : '下降'
        alerts.push({
          type: 'info',
          message: `毛利率${direction} ${Math.abs(gpa.marginChange).toFixed(1)}pp（本期 ${typeof gpa.grossMargin === 'number' ? gpa.grossMargin.toFixed(1) : 'N/A'}% → 上期 ${typeof gpa.priorGrossMargin === 'number' ? gpa.priorGrossMargin.toFixed(1) : 'N/A'}%），请关注成本变动原因`,
        })
      }
    }

    // 4. F5-2 ↔ F5-1 主营未审差异
    if (monthlyTotal.value > 0 && Math.abs(monthlyVsAdjudicationDiff.value) > 1) {
      alerts.push({
        type: 'warning',
        message: `F5-2月度合计(${monthlyTotal.value.toLocaleString('zh-CN')}) ↔ F5-1主营未审合计(${f5MainUnadjusted.value.toLocaleString('zh-CN')}) 差异 ${monthlyVsAdjudicationDiff.value.toLocaleString('zh-CN')} 元`,
        excludeSheets: ['F5-2', 'F5-1'],
      })
    }

    return alerts
  })

  // ─── 跨底稿拉取 D4 收入数据（可选，按需调用） ─────────────────────
  async function pullD4Revenue(): Promise<void> {
    if (!projectId.value) return
    try {
      // 先尝试通过项目级查 wp-id-by-code 获取 D4 的 wp_id
      const wpRes = await api.get('/api/custom-query/wp-id-by-code', {
        params: { project_id: projectId.value, wp_code: 'D4' },
        _silent: true,
      } as any)
      const d4WpId = wpRes?.data?.wp_id ?? wpRes?.wp_id
      if (!d4WpId) return

      // 从 D4 的 checklist-responses 拉取审定数据
      const res = await api.get(`/api/workpapers/${d4WpId}/checklist-responses`, { _silent: true } as any)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      let mainRevenue = 0
      let priorMainRevenue = 0
      let tbRevenue = 0

      for (const r of responses) {
        if (r.item_id === D4_MAIN_STORAGE_KEY && r.remark) {
          // D4-1 主营审定行
          mainRevenue = sumAdjusted(r.remark)
          priorMainRevenue = sumPriorAdjusted(r.remark)
        }
        if (r.item_id === D4_TB_KEY && r.remark) {
          tbRevenue = parseNum(r.remark)
        }
      }

      d4Revenue.value = mainRevenue || tbRevenue
      d4PriorRevenue.value = priorMainRevenue
      d4Loaded.value = true
    } catch {
      // D4 数据不可用时静默降级，毛利率分析为 N/A
      d4Loaded.value = false
    }
  }

  return {
    // 审定数汇总
    f5MainAdjusted,
    f5OtherAdjusted,
    f5TotalAdjusted,
    f5TotalPriorAdjusted,
    // TB 核对
    tbAmount,
    tbVariance,
    // 毛利率
    grossProfitAnalysis,
    d4Revenue,
    d4PriorRevenue,
    d4Loaded,
    pullD4Revenue,
    // 内部勾稽
    monthlyTotal,
    monthlyVsAdjudicationDiff,
    rollforwardCOGS,
    rollforwardVsAdjudicationDiff,
    // 全局告警
    globalAlerts,
  }
}

export default useF5CrossSheet
