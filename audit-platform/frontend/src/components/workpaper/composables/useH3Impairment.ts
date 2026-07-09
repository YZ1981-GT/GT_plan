/**
 * useH3Impairment — H3-10/H3-11 减值组 composable（仅成本模式）
 *
 * 减值迹象判断 + DCF模型 + 敏感性矩阵
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.15
 * Requirements: 11.1-11.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcDcfPresentValue, calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentSign {
  id: string
  description: string         // 减值迹象描述
  exists: boolean             // 是否存在
  evidence: string            // 判断证据
}

export interface ImpairmentCalcRow {
  rowId: string
  assetName: string
  bookValue: number           // 账面价值
  fairLessDisposal: number    // 公允-处置费
  dcfValue: number            // DCF现值
  recoverableAmount: number   // 可收回金额（公式：MAX(公允-费,DCF)）
  impairmentLoss: number      // 减值（公式：MAX(账面-可收回,0)）
}

export interface DcfAssumption {
  assetName: string
  cashFlows: number[]         // 未来现金流(5年)
  discountRate: number        // 折现率
  terminalGrowth: number      // 永续增长率
}

export interface SensitivityCell {
  discountRate: number
  growthRate: number
  value: number
}

const ITEM_SIGNS = 'H3-10-signs'
const ITEM_CALC = 'H3-10-calc-rows'
const ITEM_DCF = 'H3-11-dcf'

const DEFAULT_SIGNS: Omit<ImpairmentSign, 'exists' | 'evidence'>[] = [
  { id: 'vacancy', description: '长期空置' },
  { id: 'rentDrop', description: '租金持续下降' },
  { id: 'marketDecline', description: '房地产市场恶化' },
  { id: 'aging', description: '资产老旧/功能落后' },
  { id: 'policy', description: '规划/政策变化' },
]

export function useH3Impairment(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const signs = ref<ImpairmentSign[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])
  const dcfAssumptions = ref<DcfAssumption[]>([])

  function loadData(): void {
    const rawSigns = getValue(ITEM_SIGNS)
    signs.value = Array.isArray(rawSigns)
      ? rawSigns.map(_normSign)
      : DEFAULT_SIGNS.map((s) => ({ ...s, exists: false, evidence: '' }))

    const rawCalc = getValue(ITEM_CALC)
    calcRows.value = Array.isArray(rawCalc) ? rawCalc.map(_normCalc) : []

    const rawDcf = getValue(ITEM_DCF)
    dcfAssumptions.value = Array.isArray(rawDcf) ? rawDcf : []
  }

  function _normSign(raw: any): ImpairmentSign {
    return {
      id: raw.id ?? '',
      description: raw.description ?? '',
      exists: Boolean(raw.exists),
      evidence: raw.evidence ?? '',
    }
  }

  function _normCalc(raw: any): ImpairmentCalcRow {
    const book = Number(raw.bookValue) || 0
    const fair = Number(raw.fairLessDisposal) || 0
    const dcf = Number(raw.dcfValue) || 0
    const recoverable = Math.max(fair, dcf)
    return {
      rowId: raw.rowId ?? `imp-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      bookValue: book,
      fairLessDisposal: fair,
      dcfValue: dcf,
      recoverableAmount: recoverable,
      impairmentLoss: Math.max(book - recoverable, 0),
    }
  }

  /** 是否存在减值迹象 */
  const hasImpairmentSigns = computed(() => signs.value.some((s) => s.exists))
  /** 减值总额 */
  const totalImpairment = computed(() => calcSubtotal(calcRows.value.map((r) => r.impairmentLoss)))

  /** 生成敏感性矩阵 */
  function buildSensitivityMatrix(assetName: string): SensitivityCell[] {
    const assumption = dcfAssumptions.value.find((a) => a.assetName === assetName)
    if (!assumption) return []
    const rates = [-0.02, -0.01, 0, 0.01, 0.02].map((d) => assumption.discountRate + d)
    const growths = [-0.01, 0, 0.01].map((d) => assumption.terminalGrowth + d)
    const matrix: SensitivityCell[] = []
    for (const r of rates) {
      for (const g of growths) {
        matrix.push({ discountRate: r, growthRate: g, value: calcDcfPresentValue(assumption.cashFlows, r) })
      }
    }
    return matrix
  }

  function updateSign(id: string, field: 'exists' | 'evidence', value: any): void {
    const sign = signs.value.find((s) => s.id === id)
    if (sign) { (sign as any)[field] = value; setValue(ITEM_SIGNS, signs.value) }
  }

  function addCalcRow(assetName: string): void {
    calcRows.value.push(_normCalc({ assetName, rowId: `imp-${Date.now()}` }))
    setValue(ITEM_CALC, calcRows.value)
  }

  function updateCalcCell(index: number, field: keyof ImpairmentCalcRow, value: any): void {
    const row = calcRows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    const recalced = _normCalc({ ...row })
    Object.assign(row, recalced)
    setValue(ITEM_CALC, calcRows.value)
  }

  function updateDcf(assumptions: DcfAssumption[]): void {
    dcfAssumptions.value = assumptions
    setValue(ITEM_DCF, assumptions)
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    signs, calcRows, dcfAssumptions,
    hasImpairmentSigns, totalImpairment,
    buildSensitivityMatrix, updateSign, addCalcRow, updateCalcCell, updateDcf, loadData,
  }
}

export default useH3Impairment
