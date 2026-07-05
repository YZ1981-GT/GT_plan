/**
 * useF5Comparison — F5-5 与上年度比较分析表（17列）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 5.3
 * 公式链：毛利=收入-成本 / 毛利率 / 变动额/率(收入,成本) / 毛利率变动=本期毛利率-上期毛利率
 * 毛利率变动>5百分点 橙色；成本变动率与收入变动率偏差>10% 橙色(收入成本不匹配)
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcChangeAmount,
  calcChangeRate,
  calcGrossMargin,
  calcSubtotal,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5ComparisonOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface ComparisonRow {
  id: string
  product: string
  currentRevenue: number
  currentCost: number
  currentGrossProfit: number // 公式
  currentGrossMargin: number | 'N/A' // 公式
  priorRevenue: number
  priorCost: number
  priorGrossProfit: number // 公式
  priorGrossMargin: number | 'N/A' // 公式
  revenueChange: number // 公式
  revenueChangeRate: number | 'N/A' // 公式
  costChange: number // 公式
  costChangeRate: number | 'N/A' // 公式
  marginChange: number | 'N/A' // 毛利率变动(公式，百分点)
  changeReason: string
  auditEvaluation: string
  remark: string
}

interface StoredComparisonRow {
  id: string
  product: string
  currentRevenue: number
  currentCost: number
  priorRevenue: number
  priorCost: number
  changeReason: string
  auditEvaluation: string
  remark: string
}

const STORAGE_KEY = 'F5-5-comparison-rows'
const MARGIN_CHANGE_THRESHOLD = 5 // 百分点
const MISMATCH_THRESHOLD = 10 // 收入成本变动率偏差%

function safeParse(jsonStr: string | null | undefined): StoredComparisonRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => ({
      id: String(r.id ?? Date.now()),
      product: String(r.product ?? ''),
      currentRevenue: parseNum(r.currentRevenue),
      currentCost: parseNum(r.currentCost),
      priorRevenue: parseNum(r.priorRevenue),
      priorCost: parseNum(r.priorCost),
      changeReason: String(r.changeReason ?? ''),
      auditEvaluation: String(r.auditEvaluation ?? ''),
      remark: String(r.remark ?? ''),
    }))
  } catch {
    return []
  }
}

function computeRow(s: StoredComparisonRow): ComparisonRow {
  const currentGrossMargin = calcGrossMargin(s.currentRevenue, s.currentCost)
  const priorGrossMargin = calcGrossMargin(s.priorRevenue, s.priorCost)
  let marginChange: number | 'N/A' = 'N/A'
  if (currentGrossMargin !== 'N/A' && priorGrossMargin !== 'N/A') {
    marginChange = currentGrossMargin - priorGrossMargin
  }
  return {
    id: s.id,
    product: s.product,
    currentRevenue: s.currentRevenue,
    currentCost: s.currentCost,
    currentGrossProfit: s.currentRevenue - s.currentCost,
    currentGrossMargin,
    priorRevenue: s.priorRevenue,
    priorCost: s.priorCost,
    priorGrossProfit: s.priorRevenue - s.priorCost,
    priorGrossMargin,
    revenueChange: calcChangeAmount(s.currentRevenue, s.priorRevenue),
    revenueChangeRate: calcChangeRate(s.currentRevenue, s.priorRevenue),
    costChange: calcChangeAmount(s.currentCost, s.priorCost),
    costChangeRate: calcChangeRate(s.currentCost, s.priorCost),
    marginChange,
    changeReason: s.changeReason,
    auditEvaluation: s.auditEvaluation,
    remark: s.remark,
  }
}

export function useF5Comparison(options: UseF5ComparisonOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? computed(() => false)

  const storedRows = computed<StoredComparisonRow[]>(() =>
    safeParse(allResponses.value.get(STORAGE_KEY)?.remark),
  )

  const rows: ComputedRef<ComparisonRow[]> = computed(() => storedRows.value.map(computeRow))

  const totalRow = computed(() => {
    const cr = calcSubtotal(storedRows.value.map((r) => r.currentRevenue))
    const cc = calcSubtotal(storedRows.value.map((r) => r.currentCost))
    const pr = calcSubtotal(storedRows.value.map((r) => r.priorRevenue))
    const pc = calcSubtotal(storedRows.value.map((r) => r.priorCost))
    return {
      currentRevenue: cr,
      currentCost: cc,
      currentGrossProfit: cr - cc,
      currentGrossMargin: calcGrossMargin(cr, cc),
      priorRevenue: pr,
      priorCost: pc,
      priorGrossProfit: pr - pc,
      priorGrossMargin: calcGrossMargin(pr, pc),
    }
  })

  /** 毛利率变动>5百分点 高亮 */
  function isMarginChangeHigh(row: ComparisonRow): boolean {
    return row.marginChange !== 'N/A' && Math.abs(row.marginChange) > MARGIN_CHANGE_THRESHOLD
  }

  /** 收入成本不匹配：成本变动率与收入变动率偏差>10% */
  function isMismatch(row: ComparisonRow): boolean {
    if (row.revenueChangeRate === 'N/A' || row.costChangeRate === 'N/A') return false
    return Math.abs(row.costChangeRate - row.revenueChangeRate) > MISMATCH_THRESHOLD
  }

  function isRowHighlighted(row: ComparisonRow): boolean {
    return isMarginChangeHigh(row) || isMismatch(row)
  }

  function persist(rows: StoredComparisonRow[]): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows) })
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === id)
    if (idx === -1) return
    const numericKeys = ['currentRevenue', 'currentCost', 'priorRevenue', 'priorCost']
    if (numericKeys.includes(key)) {
      ;(stored[idx] as any)[key] = parseNum(value)
    } else {
      ;(stored[idx] as any)[key] = String(value ?? '')
    }
    persist(stored)
  }

  function addRow(product: string): void {
    if (readonly.value || !product) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    stored.push({
      id: `cmp-${Date.now()}`,
      product,
      currentRevenue: 0,
      currentCost: 0,
      priorRevenue: 0,
      priorCost: 0,
      changeReason: '',
      auditEvaluation: '',
      remark: '',
    })
    persist(stored)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    persist(safeParse(allResponses.value.get(STORAGE_KEY)?.remark).filter((r) => r.id !== id))
  }

  return { rows, totalRow, isRowHighlighted, isMarginChangeHigh, isMismatch, updateCell, addRow, removeRow }
}

export default useF5Comparison
