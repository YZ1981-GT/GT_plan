/**
 * useH3Impairment — H3-10/H3-11 减值组 composable（仅成本模式）
 *
 * H3-10：减值迹象判断 + 减值测算表
 * H3-11：DCF 模型（假设 + 现金流预测 + 敏感性矩阵）
 *
 * 字段命名与 H3TabImpairment.vue / H3TabRecoverable.vue 模板保持一致。
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.15
 * Requirements: 11.1-11.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentSign {
  id: string
  indicator: string           // 减值迹象描述
  exists: string              // 是否存在（是/否/不适用）
  evidence: string            // 判断依据
}

export interface ImpairmentCalcRow {
  rowId: string
  assetName: string
  bookValue: number           // 账面价值
  recoverableAmount: number   // 可收回金额（可手工录入或联动 H3-11）
  impairmentLoss: number      // 减值（公式：MAX(账面-可收回,0)）
  remark: string
}

export interface DcfAssumptions {
  discountRate: number        // 折现率(%)
  forecastYears: number       // 预测期(年)
  terminalGrowth: number      // 永续增长率(%)
  annualRent: number          // 年租金收入
  annualCost: number          // 年运营成本
  residualValue: number       // 残值
}

export interface CashFlowRow {
  year: number
  revenue: number
  cost: number
  netCashFlow: number
  discountFactor: number
  presentValue: number
}

const ITEM_SIGNS = 'H3-10-signs'
const ITEM_CALC = 'H3-10-calc-rows'
const ITEM_DCF = 'H3-11-dcf-assumptions'

const DEFAULT_SIGNS: { id: string; indicator: string }[] = [
  { id: 'vacancy', indicator: '长期空置' },
  { id: 'rentDrop', indicator: '租金持续下降' },
  { id: 'marketDecline', indicator: '房地产市场恶化' },
  { id: 'aging', indicator: '资产老旧/功能落后' },
  { id: 'policy', indicator: '规划/政策变化' },
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

  // ─── H3-10 状态 ──────────────────────────────────────────────────────────────
  const signs = ref<ImpairmentSign[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])

  // ─── H3-11 状态 ──────────────────────────────────────────────────────────────
  const assumptions = ref<DcfAssumptions>({
    discountRate: 0,
    forecastYears: 5,
    terminalGrowth: 0,
    annualRent: 0,
    annualCost: 0,
    residualValue: 0,
  })

  function loadData(): void {
    const rawSigns = getValue(ITEM_SIGNS)
    signs.value = Array.isArray(rawSigns)
      ? rawSigns.map(_normSign)
      : DEFAULT_SIGNS.map((s) => ({ id: s.id, indicator: s.indicator, exists: '', evidence: '' }))

    const rawCalc = getValue(ITEM_CALC)
    calcRows.value = Array.isArray(rawCalc) ? rawCalc.map(_normCalc) : []

    const rawDcf = getValue(ITEM_DCF)
    if (rawDcf && typeof rawDcf === 'object' && !Array.isArray(rawDcf)) {
      assumptions.value = {
        discountRate: Number(rawDcf.discountRate) || 0,
        forecastYears: Number(rawDcf.forecastYears) || 5,
        terminalGrowth: Number(rawDcf.terminalGrowth) || 0,
        annualRent: Number(rawDcf.annualRent) || 0,
        annualCost: Number(rawDcf.annualCost) || 0,
        residualValue: Number(rawDcf.residualValue) || 0,
      }
    }
  }

  function _normSign(raw: any): ImpairmentSign {
    return {
      id: raw.id ?? '',
      indicator: raw.indicator ?? raw.description ?? '',
      exists: typeof raw.exists === 'string' ? raw.exists : (raw.exists ? '是' : ''),
      evidence: raw.evidence ?? '',
    }
  }

  function _normCalc(raw: any): ImpairmentCalcRow {
    const book = Number(raw.bookValue) || 0
    const recoverable = Number(raw.recoverableAmount) || 0
    return {
      rowId: raw.rowId ?? `imp-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      bookValue: book,
      recoverableAmount: recoverable,
      impairmentLoss: Math.max(book - recoverable, 0),
      remark: raw.remark ?? '',
    }
  }

  // ─── H3-10 computed ──────────────────────────────────────────────────────────
  /** 是否存在减值迹象 */
  const hasImpairmentSigns = computed(() => signs.value.some((s) => s.exists === '是'))
  /** 减值总额 */
  const totalImpairment = computed(() => calcSubtotal(calcRows.value.map((r) => r.impairmentLoss)))

  // ─── H3-10 操作 ────────────────────────────────────────────────────────────────
  /** 减值迹象变更：组件已 v-model 就地修改，持久化（组件调用 updateSign(index, row)） */
  function updateSign(_index: number, _row?: any): void {
    setValue(ITEM_SIGNS, signs.value)
  }

  function addCalcRow(assetName?: string): void {
    calcRows.value.push(_normCalc({ assetName: assetName ?? '', rowId: `imp-${Date.now()}` }))
    setValue(ITEM_CALC, calcRows.value)
  }

  /** 减值测算行变更：重算减值损失并持久化（组件调用 updateCalcRow(index, row)） */
  function updateCalcRow(index: number, _row?: any): void {
    const row = calcRows.value[index]
    if (!row) return
    row.bookValue = Number(row.bookValue) || 0
    row.recoverableAmount = Number(row.recoverableAmount) || 0
    row.impairmentLoss = Math.max(row.bookValue - row.recoverableAmount, 0)
    setValue(ITEM_CALC, calcRows.value)
  }

  // ─── H3-11 DCF computed ───────────────────────────────────────────────────────
  /** 现金流预测表 */
  const cashFlowRows = computed<CashFlowRow[]>(() => {
    const a = assumptions.value
    const years = Math.max(0, Math.floor(Number(a.forecastYears) || 0))
    const dr = (Number(a.discountRate) || 0) / 100
    const revenue = Number(a.annualRent) || 0
    const cost = Number(a.annualCost) || 0
    const residual = Number(a.residualValue) || 0
    const out: CashFlowRow[] = []
    for (let y = 1; y <= years; y++) {
      const net = revenue - cost + (y === years ? residual : 0)
      const df = 1 / Math.pow(1 + dr, y)
      out.push({ year: y, revenue, cost, netCashFlow: net, discountFactor: df, presentValue: net * df })
    }
    return out
  })

  /** DCF 现值合计 */
  const dcfTotal = computed(() => calcSubtotal(cashFlowRows.value.map((r) => r.presentValue)))

  /** 可收回金额（无「公允-处置费」录入项时取 DCF 现值） */
  const recoverableAmount = computed(() => Math.max(dcfTotal.value, 0))

  /** 单点 DCF 测算（供敏感性矩阵） */
  function _computeDcfAt(discountRatePct: number, growthPct: number): number {
    const a = assumptions.value
    const years = Math.max(0, Math.floor(Number(a.forecastYears) || 0))
    const dr = (discountRatePct || 0) / 100
    const g = (growthPct || 0) / 100
    const net = (Number(a.annualRent) || 0) - (Number(a.annualCost) || 0)
    const residual = Number(a.residualValue) || 0
    if (years <= 0) return 0
    let pv = 0
    for (let y = 1; y <= years; y++) {
      pv += (net + (y === years ? residual : 0)) / Math.pow(1 + dr, y)
    }
    // 永续价值（dr>g 时）在预测期末折现
    if (dr > g) {
      const terminal = (net * (1 + g)) / (dr - g)
      pv += terminal / Math.pow(1 + dr, years)
    }
    return pv
  }

  /** 敏感性列（永续增长率 ±1个百分点） */
  const sensitivityCols = computed<string[]>(() => {
    const g = Number(assumptions.value.terminalGrowth) || 0
    return [g - 1, g, g + 1].map((x) => x.toFixed(1))
  })

  /** 敏感性矩阵行（折现率 ±1个百分点 × 增长率列） */
  const sensitivityRows = computed(() => {
    const dr = Number(assumptions.value.discountRate) || 0
    return [dr - 1, dr, dr + 1].map((d) => {
      const row: Record<string, any> = { label: `${d.toFixed(1)}%` }
      for (const col of sensitivityCols.value) {
        row[col] = _computeDcfAt(d, parseFloat(col))
      }
      return row
    })
  })

  // ─── H3-11 操作 ────────────────────────────────────────────────────────────────
  /** 假设变更：组件已 v-model 就地修改 assumptions，此处持久化（现值/矩阵为 computed 自动更新） */
  function updateAssumptions(_a?: any): void {
    setValue(ITEM_DCF, assumptions.value)
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    // H3-10
    signs, calcRows,
    impairmentSigns: signs,
    impairmentCalcRows: calcRows,
    hasImpairmentSigns, totalImpairment,
    updateSign, addCalcRow, updateCalcRow,
    // H3-11
    assumptions, cashFlowRows, dcfTotal, recoverableAmount,
    sensitivityRows, sensitivityCols, updateAssumptions,
    loadData,
  }
}

export default useH3Impairment
