/**
 * useF5OtherCost — F5-3 其他业务成本明细（14列）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 5.2
 * 公式链：变动额=本期-上期 / 变动率 / 占比=本期/合计 / 成本率=本期/对应收入
 * 变动率绝对值>30% 橙色标记
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5OtherCostOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface OtherCostRow {
  id: string
  seq: number
  costItem: string
  currentAmount: number
  priorAmount: number
  changeAmount: number // 公式
  changeRate: number | 'N/A' // 公式
  proportion: number | 'N/A' // 占比(公式)
  correspondingRevenue: number
  costRate: number | 'N/A' // 公式=本期/对应收入
  revenueRecognitionTiming: string
  costRecognitionTiming: string
  matchingReasonability: string
  auditEvaluation: string
  remark: string
}

interface StoredOtherCostRow {
  id: string
  costItem: string
  currentAmount: number
  priorAmount: number
  correspondingRevenue: number
  revenueRecognitionTiming: string
  costRecognitionTiming: string
  matchingReasonability: string
  auditEvaluation: string
  remark: string
}

const STORAGE_KEY = 'F5-3-other-cost-rows'
const CHANGE_RATE_THRESHOLD = 30

function safeParse(jsonStr: string | null | undefined): StoredOtherCostRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => ({
      id: String(r.id ?? Date.now()),
      costItem: String(r.costItem ?? ''),
      currentAmount: parseNum(r.currentAmount),
      priorAmount: parseNum(r.priorAmount),
      correspondingRevenue: parseNum(r.correspondingRevenue),
      revenueRecognitionTiming: String(r.revenueRecognitionTiming ?? ''),
      costRecognitionTiming: String(r.costRecognitionTiming ?? ''),
      matchingReasonability: String(r.matchingReasonability ?? ''),
      auditEvaluation: String(r.auditEvaluation ?? ''),
      remark: String(r.remark ?? ''),
    }))
  } catch {
    return []
  }
}

export function useF5OtherCost(options: UseF5OtherCostOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? computed(() => false)

  const storedRows = computed<StoredOtherCostRow[]>(() =>
    safeParse(allResponses.value.get(STORAGE_KEY)?.remark),
  )

  const totalCurrent = computed(() => calcSubtotal(storedRows.value.map((r) => r.currentAmount)))

  const rows: ComputedRef<OtherCostRow[]> = computed(() =>
    storedRows.value.map((s, i) => {
      const changeAmount = calcChangeAmount(s.currentAmount, s.priorAmount)
      return {
        id: s.id,
        seq: i + 1,
        costItem: s.costItem,
        currentAmount: s.currentAmount,
        priorAmount: s.priorAmount,
        changeAmount,
        changeRate: calcChangeRate(s.currentAmount, s.priorAmount),
        proportion: totalCurrent.value === 0 ? 'N/A' : (s.currentAmount / totalCurrent.value) * 100,
        correspondingRevenue: s.correspondingRevenue,
        costRate: s.correspondingRevenue === 0 ? 'N/A' : (s.currentAmount / s.correspondingRevenue) * 100,
        revenueRecognitionTiming: s.revenueRecognitionTiming,
        costRecognitionTiming: s.costRecognitionTiming,
        matchingReasonability: s.matchingReasonability,
        auditEvaluation: s.auditEvaluation,
        remark: s.remark,
      }
    }),
  )

  const totalRow = computed(() => ({
    currentAmount: totalCurrent.value,
    priorAmount: calcSubtotal(storedRows.value.map((r) => r.priorAmount)),
    changeAmount: calcChangeAmount(
      totalCurrent.value,
      calcSubtotal(storedRows.value.map((r) => r.priorAmount)),
    ),
  }))

  function isRowHighlighted(row: OtherCostRow): boolean {
    return row.changeRate !== 'N/A' && Math.abs(row.changeRate) > CHANGE_RATE_THRESHOLD
  }

  function persist(rows: StoredOtherCostRow[]): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows) })
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === id)
    if (idx === -1) return
    const numericKeys = ['currentAmount', 'priorAmount', 'correspondingRevenue']
    if (numericKeys.includes(key)) {
      ;(stored[idx] as any)[key] = parseNum(value)
    } else {
      ;(stored[idx] as any)[key] = String(value ?? '')
    }
    persist(stored)
  }

  function addRow(): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    stored.push({
      id: `oc-${Date.now()}`,
      costItem: '',
      currentAmount: 0,
      priorAmount: 0,
      correspondingRevenue: 0,
      revenueRecognitionTiming: '',
      costRecognitionTiming: '',
      matchingReasonability: '',
      auditEvaluation: '',
      remark: '',
    })
    persist(stored)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    persist(safeParse(allResponses.value.get(STORAGE_KEY)?.remark).filter((r) => r.id !== id))
  }

  return { rows, totalRow, isRowHighlighted, updateCell, addRow, removeRow }
}

export default useF5OtherCost
