/**
 * useS21FormulaEngine — S21 数据资产开发支出资本化公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - 按月归集：各类目 12 月金额横向求和 → 类目合计
 * - 类目占比：类目合计 / 资本化总额
 * - 各月合计：各类目该月纵向求和
 * - 各月比例：月合计 / 资本化总额
 * - 研发阶段合计：研究阶段 SUM / 开发阶段 SUM
 *
 * 公式来源（S21-2 开发支出资本化分析表）：
 * - 类目合计 N{r} = SUM(B{r}:M{r})
 * - 类目占比 O{r} = N{r} / $N$40
 * - 月合计 {c}26 = SUM({c}18:{c}25)
 * - 总额 N26 = SUM(B26:M26)
 * - 各月比例 {c}27 = {c}26 / $N$40
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 3.3
 * Requirements: 5.1, 5.2, 5.3
 */

import { computed, type Ref } from 'vue'

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 规范化月度数组为恰好 12 元素
 * - 短于 12 → 尾部补 0
 * - 长于 12 → 截断为前 12 个
 * - 每个元素经 parseNum 安全化
 */
function normalizeMonthly(arr: number[] | undefined | null): number[] {
  const raw = Array.isArray(arr) ? arr : []
  const result: number[] = []
  for (let i = 0; i < 12; i++) {
    result.push(i < raw.length ? parseNum(raw[i]) : 0)
  }
  return result
}

// ─── interfaces ─────────────────────────────────────────────

export interface CapitalizationInput {
  monthly: Record<string, number[]>  // 类目名 → 12 月金额 (index 0=1月, 11=12月)
}

export interface CapitalizationResult {
  categoryTotals: Record<string, number>   // 各类目合计 = SUM(12月)
  total: number                            // 资本化总额 = SUM(所有类目合计)
  categoryRatios: Record<string, number>   // 各类目占比 = categoryTotals[k] / total
  monthlyTotals: number[]                  // 各月合计 = SUM(各类目该月) [12 elements]
  monthlyRatios: number[]                  // 各月比例 = monthlyTotals[m] / total [12 elements]
  unable: boolean                          // total=0 时 true (占比不可计算)
}

export interface ResearchDevInput {
  researchItems: number[]    // 研究阶段各项支出
  developmentItems: number[] // 开发阶段各项支出
}

export interface ResearchDevResult {
  researchTotal: number      // 研究阶段合计 = SUM(researchItems)
  developmentTotal: number   // 开发阶段合计 = SUM(developmentItems)
}

// ─── 1. 资本化金额按月归集（Property P6） ───────────────────

/**
 * 计算开发支出资本化按月归集、类目合计、占比、月合计、月比例
 *
 * 公式链（来源：S21-2 开发支出资本化分析表 区段二）：
 * - categoryTotals[k] = SUM(monthly[k][0..11])         → N{r}
 * - total = SUM(所有 categoryTotals)                   → N26
 * - categoryRatios[k] = categoryTotals[k] / total      → O{r}
 * - monthlyTotals[m] = SUM(所有类目 monthly[k][m])     → {c}26
 * - monthlyRatios[m] = monthlyTotals[m] / total        → {c}27
 *
 * 错误处理：
 * - total=0 → unable=true，所有 ratios 为 0
 * - 空 monthly → total=0
 * - 月数组不足 12 元素 → 补 0；超过 12 → 截断
 * - 绝不抛异常，绝不返回 NaN/Infinity
 *
 * @param i - CapitalizationInput
 * @returns CapitalizationResult
 */
export function calcCapitalization(i: CapitalizationInput): CapitalizationResult {
  const monthly = i.monthly && typeof i.monthly === 'object' ? i.monthly : {}
  const keys = Object.keys(monthly)

  // 规范化各类目月度数组
  const normalized: Record<string, number[]> = {}
  for (const k of keys) {
    normalized[k] = normalizeMonthly(monthly[k])
  }

  // 各类目合计 = SUM(12月)
  const categoryTotals: Record<string, number> = {}
  for (const k of keys) {
    categoryTotals[k] = normalized[k].reduce((sum, v) => sum + v, 0)
  }

  // 资本化总额 = SUM(所有类目合计)
  let total = 0
  for (const k of keys) {
    total += categoryTotals[k]
  }

  // 各月合计 = SUM(各类目该月)
  const monthlyTotals: number[] = []
  for (let m = 0; m < 12; m++) {
    let monthSum = 0
    for (const k of keys) {
      monthSum += normalized[k][m]
    }
    monthlyTotals.push(monthSum)
  }

  // 分母零保护
  const unable = total === 0

  // 各类目占比 = categoryTotals[k] / total
  const categoryRatios: Record<string, number> = {}
  for (const k of keys) {
    categoryRatios[k] = unable ? 0 : categoryTotals[k] / total
  }

  // 各月比例 = monthlyTotals[m] / total
  const monthlyRatios: number[] = []
  for (let m = 0; m < 12; m++) {
    monthlyRatios.push(unable ? 0 : monthlyTotals[m] / total)
  }

  return {
    categoryTotals,
    total,
    categoryRatios,
    monthlyTotals,
    monthlyRatios,
    unable,
  }
}

// ─── 2. 研发阶段合计（Req 5.3） ────────────────────────────

/**
 * 计算研究阶段 / 开发阶段各项支出合计
 *
 * 来源：S21-2 区段一 row7-15
 * - 研究阶段合计 = SUM(researchItems)
 * - 开发阶段合计 = SUM(developmentItems)
 *
 * @param i - ResearchDevInput
 * @returns ResearchDevResult
 */
export function calcResearchDevTotals(i: ResearchDevInput): ResearchDevResult {
  const researchArr = Array.isArray(i.researchItems) ? i.researchItems : []
  const devArr = Array.isArray(i.developmentItems) ? i.developmentItems : []

  const researchTotal = researchArr.reduce((sum, v) => sum + parseNum(v), 0)
  const developmentTotal = devArr.reduce((sum, v) => sum + parseNum(v), 0)

  return { researchTotal, developmentTotal }
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * Vue composable wrapper — 将纯函数以 reactive 方式暴露给组件
 *
 * 使用方式：
 * ```ts
 * const { capitalization, researchDev } = useS21FormulaEngine(capInputRef, rdInputRef)
 * // capitalization.value.total / capitalization.value.categoryRatios / ...
 * // researchDev.value.researchTotal / ...
 * ```
 */
export function useS21FormulaEngine(
  capInput?: Ref<CapitalizationInput>,
  rdInput?: Ref<ResearchDevInput>,
) {
  const capitalization = computed<CapitalizationResult>(() => {
    if (!capInput?.value) {
      return {
        categoryTotals: {},
        total: 0,
        categoryRatios: {},
        monthlyTotals: new Array(12).fill(0),
        monthlyRatios: new Array(12).fill(0),
        unable: true,
      }
    }
    return calcCapitalization(capInput.value)
  })

  const researchDev = computed<ResearchDevResult>(() => {
    if (!rdInput?.value) {
      return { researchTotal: 0, developmentTotal: 0 }
    }
    return calcResearchDevTotals(rdInput.value)
  })

  return {
    // 纯函数（直接导出供独立调用）
    calcCapitalization,
    calcResearchDevTotals,
    parseNum,
    // reactive computeds
    capitalization,
    researchDev,
  }
}
