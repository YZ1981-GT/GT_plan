/**
 * useI2Impairment — I2-15 减值准备测试表 + I2-16 可收回金额测试(DCF)
 *
 * 核心功能：
 * 1. I2-15 减值准备测试表：
 *    - 列：项目|账面|可收回金额|应计提|已计提|差额 (Req 10.1)
 *    - 公式：应计提=MAX(账面-可收回,0); 差额=应计提-已计提
 *    - 差额≠0 红色高亮
 * 2. I2-16 可收回金额测试（DCF，复用I1-13模式）(Req 10.2)：
 *    - DCF模型：预测期现金流(5年) + 折现率 + 终值 + 现值合计
 *    - 公式：PV=Σ(CF_i/(1+r)^i) + TV/(1+r)^n
 *    - 可收回金额=MAX(公允价值-处置费用, DCF使用价值)
 * 3. I2-16 → I2-15 联动：可收回金额自动填入对应行
 * 4. 联动审定表减值准备列 (Req 10.3)
 *
 * 持久化：
 * - I2-15 rows: "I2-15-rows"
 * - I2-16 DCF params: "I2-16-dcf-params"
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.7
 * Requirements: 10.1-10.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI2FormData'

// ─── Types: I2-15 减值准备测试 ───────────────────────────────────────────────

/** I2-15 减值准备测试行 (Req 10.1) */
export interface I2ImpairmentTestRow {
  rowId: string
  /** 研发项目名称 */
  name: string
  /** 账面价值（开发支出净值） */
  bookValue: number
  /** 可收回金额（从 I2-16 联动填入，或手工输入）*/
  recoverableAmount: number
  /** 应计提减值 = MAX(账面 - 可收回, 0) */
  shouldProvision: number
  /** 已计提减值 */
  alreadyProvided: number
  /** 差额 = 应计提 - 已计提 */
  difference: number
  /** 审计结论 */
  conclusion: string
  /** 是否关联 I2-16 DCF 测试 */
  linkedToDcf: boolean
}

// ─── Types: I2-16 可收回金额测试 (DCF) ──────────────────────────────────────

/** DCF 预测期年数 */
export const DCF_FORECAST_YEARS = 5

/** I2-16 可收回金额测试行 (Req 10.2) */
export interface I2RecoverableTestRow {
  rowId: string
  /** 资产/项目名称（与 I2-15 对应） */
  name: string
  /** 预测期现金流数组（5年） */
  cashFlows: number[]
  /** 折现率 (如 0.08=8%) */
  discountRate: number
  /** 永续增长率 (如 0.02=2%) */
  growthRate: number
  /** 终值 = perpetuityCF / (r - g) */
  terminalValue: number
  /** DCF 使用价值 = PV(预测期) + PV(终值) */
  valueInUse: number
  /** 公允价值减去处置费用 */
  fairValueLessDisposal: number
  /** 可收回金额 = MAX(公允-处置费, DCF) */
  recoverableAmount: number
  /** 各期折现现金流（明细展示） */
  discountedCashFlows: number[]
  /** 终值折现值 */
  discountedTerminalValue: number
}

/** I2-15 合计行 */
export interface I2ImpairmentSummary {
  totalBookValue: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalDifference: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_15_ROWS = 'I2-15-rows'
const ITEM_ID_16_DCF_PARAMS = 'I2-16-dcf-params'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _genRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParseRows<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** DCF: 各期折现现值合计 */
function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (discountRate <= 0) return cashFlows.reduce((s, v) => s + v, 0)
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

/** DCF: 终值 (Gordon Growth Model) */
function calcTerminalValue(perpetuityCF: number, discountRate: number, growthRate: number): number {
  if (discountRate <= growthRate || discountRate <= 0) return 0
  return perpetuityCF / (discountRate - growthRate)
}

/** 可收回金额 = MAX(公允-处置费, DCF使用价值) */
function calcRecoverableAmount(fairValueLessDisposal: number, valueInUse: number): number {
  return Math.max(fairValueLessDisposal, valueInUse)
}

/** 减值金额 = MAX(账面 - 可收回, 0) */
function calcImpairmentAmount(bookValue: number, recoverableAmount: number): number {
  return Math.max(bookValue - recoverableAmount, 0)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 保存回调（委托 useI2FormData.saveResponse） */
    onSave?: (itemId: string, value: any) => void
  },
) {

  // ─── State: I2-15 减值准备测试 ─────────────────────────────────────────────

  const impairmentRows = ref<I2ImpairmentTestRow[]>([])

  // ─── State: I2-16 可收回金额测试 ───────────────────────────────────────────

  const recoverableRows = ref<I2RecoverableTestRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadImpairmentRows(): void {
    const resp = allResponses.value.get(ITEM_ID_15_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    impairmentRows.value = _safeParseRows<any>(raw).map(_normalizeImpairmentRow)
  }

  function _loadRecoverableRows(): void {
    const resp = allResponses.value.get(ITEM_ID_16_DCF_PARAMS)
    const raw = resp?.remark ?? resp?.conclusion
    recoverableRows.value = _safeParseRows<any>(raw).map(_normalizeRecoverableRow)
  }

  function _normalizeImpairmentRow(raw: any): I2ImpairmentTestRow {
    const bookValue = _getNum(raw.bookValue)
    const recoverableAmount = _getNum(raw.recoverableAmount)
    const shouldProvision = calcImpairmentAmount(bookValue, recoverableAmount)
    const alreadyProvided = _getNum(raw.alreadyProvided)
    const difference = shouldProvision - alreadyProvided

    return {
      rowId: raw.rowId ?? _genRowId('i2imp15'),
      name: raw.name ?? '',
      bookValue,
      recoverableAmount,
      shouldProvision,
      alreadyProvided,
      difference,
      conclusion: raw.conclusion ?? '',
      linkedToDcf: raw.linkedToDcf ?? false,
    }
  }

  function _normalizeRecoverableRow(raw: any): I2RecoverableTestRow {
    const cashFlows: number[] = Array.isArray(raw.cashFlows)
      ? raw.cashFlows.slice(0, DCF_FORECAST_YEARS).map(_getNum)
      : new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = _getNum(raw.discountRate)
    const growthRate = _getNum(raw.growthRate)
    const fairValueLessDisposal = _getNum(raw.fairValueLessDisposal)

    const { terminalValue, valueInUse, recoverableAmount, discountedCashFlows, discountedTerminalValue } =
      _calcDcfResult(cashFlows, discountRate, growthRate, fairValueLessDisposal)

    return {
      rowId: raw.rowId ?? _genRowId('i2dcf16'),
      name: raw.name ?? '',
      cashFlows,
      discountRate,
      growthRate,
      terminalValue,
      valueInUse,
      fairValueLessDisposal,
      recoverableAmount,
      discountedCashFlows,
      discountedTerminalValue,
    }
  }

  // ─── DCF Calculation Core (Req 10.2) ───────────────────────────────────────

  function _calcDcfResult(
    cashFlows: number[],
    discountRate: number,
    growthRate: number,
    fairValueLessDisposal: number,
  ): {
    terminalValue: number
    valueInUse: number
    recoverableAmount: number
    discountedCashFlows: number[]
    discountedTerminalValue: number
  } {
    const discountedCashFlows: number[] = []
    if (discountRate > 0) {
      for (let i = 0; i < cashFlows.length; i++) {
        discountedCashFlows.push(cashFlows[i] / Math.pow(1 + discountRate, i + 1))
      }
    } else {
      for (const cf of cashFlows) discountedCashFlows.push(cf)
    }

    const pvForecast = calcDcfPresentValue(cashFlows, discountRate)

    const lastCF = cashFlows.length > 0 ? cashFlows[cashFlows.length - 1] : 0
    const perpetuityCF = lastCF * (1 + growthRate)
    const terminalValue = calcTerminalValue(perpetuityCF, discountRate, growthRate)

    const n = cashFlows.length
    const discountedTerminalValue = discountRate > 0 && n > 0
      ? terminalValue / Math.pow(1 + discountRate, n)
      : terminalValue

    const valueInUse = pvForecast + discountedTerminalValue
    const recoverableAmount = calcRecoverableAmount(fairValueLessDisposal, valueInUse)

    return { terminalValue, valueInUse, recoverableAmount, discountedCashFlows, discountedTerminalValue }
  }

  // ─── I2-15: Recalculation ──────────────────────────────────────────────────

  function _recalcImpairmentRow(row: I2ImpairmentTestRow): void {
    row.shouldProvision = calcImpairmentAmount(row.bookValue, row.recoverableAmount)
    row.difference = row.shouldProvision - row.alreadyProvided
  }

  function recalcAllImpairment(): void {
    for (const row of impairmentRows.value) _recalcImpairmentRow(row)
    _persistImpairment()
  }

  // ─── I2-16: Recalculation ──────────────────────────────────────────────────

  function _recalcRecoverableRow(row: I2RecoverableTestRow): void {
    const result = _calcDcfResult(row.cashFlows, row.discountRate, row.growthRate, row.fairValueLessDisposal)
    row.terminalValue = result.terminalValue
    row.valueInUse = result.valueInUse
    row.recoverableAmount = result.recoverableAmount
    row.discountedCashFlows = result.discountedCashFlows
    row.discountedTerminalValue = result.discountedTerminalValue
  }

  function recalcAllRecoverable(): void {
    for (const row of recoverableRows.value) _recalcRecoverableRow(row)
    _persistRecoverable()
    linkRecoverableToImpairment()
  }

  // ─── I2-16 → I2-15 联动 (Req 10.3) ────────────────────────────────────────

  function linkRecoverableToImpairment(): void {
    const recoverableMap = new Map<string, number>()
    for (const row of recoverableRows.value) {
      if (row.name) recoverableMap.set(row.name, row.recoverableAmount)
    }

    let changed = false
    for (const row of impairmentRows.value) {
      if (row.linkedToDcf && row.name && recoverableMap.has(row.name)) {
        const newVal = recoverableMap.get(row.name)!
        if (row.recoverableAmount !== newVal) {
          row.recoverableAmount = newVal
          _recalcImpairmentRow(row)
          changed = true
        }
      }
    }
    if (changed) _persistImpairment()
  }

  function linkSingleRecoverableToImpairment(recoverableRowIndex: number): void {
    const rcRow = recoverableRows.value[recoverableRowIndex]
    if (!rcRow?.name) return
    for (const impRow of impairmentRows.value) {
      if (impRow.linkedToDcf && impRow.name === rcRow.name) {
        impRow.recoverableAmount = rcRow.recoverableAmount
        _recalcImpairmentRow(impRow)
      }
    }
    _persistImpairment()
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const impairmentSummary: ComputedRef<I2ImpairmentSummary> = computed(() => {
    let totalBookValue = 0
    let totalShouldProvision = 0
    let totalAlreadyProvided = 0
    let totalDifference = 0
    for (const row of impairmentRows.value) {
      totalBookValue += row.bookValue
      totalShouldProvision += row.shouldProvision
      totalAlreadyProvided += row.alreadyProvided
      totalDifference += row.difference
    }
    return { totalBookValue, totalShouldProvision, totalAlreadyProvided, totalDifference }
  })

  /** 差额≠0的行 rowId 集合（红色高亮用） */
  const highlightedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of impairmentRows.value) {
      if (Math.abs(row.difference) > 0.005) ids.add(row.rowId)
    }
    return ids
  })

  // ─── Row Management: I2-15 ─────────────────────────────────────────────────

  function addImpairmentRow(params: {
    name: string
    bookValue: number
    recoverableAmount?: number
    alreadyProvided?: number
    linkedToDcf?: boolean
  }): I2ImpairmentTestRow {
    const bookValue = params.bookValue
    const recoverableAmount = params.recoverableAmount ?? 0
    const shouldProvision = calcImpairmentAmount(bookValue, recoverableAmount)
    const alreadyProvided = params.alreadyProvided ?? 0

    const row: I2ImpairmentTestRow = {
      rowId: _genRowId('i2imp15'),
      name: params.name,
      bookValue,
      recoverableAmount,
      shouldProvision,
      alreadyProvided,
      difference: shouldProvision - alreadyProvided,
      conclusion: '',
      linkedToDcf: params.linkedToDcf ?? false,
    }
    impairmentRows.value.push(row)
    _persistImpairment()
    return row
  }

  function removeImpairmentRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= impairmentRows.value.length) return
    impairmentRows.value.splice(rowIndex, 1)
    _persistImpairment()
  }

  function updateImpairmentField(
    rowIndex: number,
    field: keyof I2ImpairmentTestRow,
    value: number | string | boolean,
  ): void {
    const row = impairmentRows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    _recalcImpairmentRow(row)
    _persistImpairment()
  }

  // ─── Row Management: I2-16 ─────────────────────────────────────────────────

  function addRecoverableRow(params: {
    name: string
    cashFlows?: number[]
    discountRate?: number
    growthRate?: number
    fairValueLessDisposal?: number
  }): I2RecoverableTestRow {
    const cashFlows = params.cashFlows?.slice(0, DCF_FORECAST_YEARS) ?? new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = params.discountRate ?? 0.08
    const growthRate = params.growthRate ?? 0.02
    const fairValueLessDisposal = params.fairValueLessDisposal ?? 0

    const result = _calcDcfResult(cashFlows, discountRate, growthRate, fairValueLessDisposal)

    const row: I2RecoverableTestRow = {
      rowId: _genRowId('i2dcf16'),
      name: params.name,
      cashFlows,
      discountRate,
      growthRate,
      ...result,
      fairValueLessDisposal,
    }
    recoverableRows.value.push(row)
    _persistRecoverable()
    return row
  }

  function removeRecoverableRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= recoverableRows.value.length) return
    recoverableRows.value.splice(rowIndex, 1)
    _persistRecoverable()
  }

  function updateCashFlow(rowIndex: number, yearIndex: number, value: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row || yearIndex < 0 || yearIndex >= DCF_FORECAST_YEARS) return
    row.cashFlows[yearIndex] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  function updateRecoverableField(
    rowIndex: number,
    field: 'discountRate' | 'growthRate' | 'fairValueLessDisposal',
    value: number,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    row[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistImpairment(): void {
    options?.onSave?.(ITEM_ID_15_ROWS, impairmentRows.value)
  }

  function _persistRecoverable(): void {
    options?.onSave?.(ITEM_ID_16_DCF_PARAMS, recoverableRows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => {
    _loadImpairmentRows()
    _loadRecoverableRows()
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    impairmentRows,
    recoverableRows,
    // Computed
    impairmentSummary,
    highlightedRowIds,
    // Constants
    DCF_FORECAST_YEARS,
    // Actions: I2-15
    recalcAllImpairment,
    addImpairmentRow,
    removeImpairmentRow,
    updateImpairmentField,
    // Actions: I2-16 DCF
    recalcAllRecoverable,
    addRecoverableRow,
    removeRecoverableRow,
    updateCashFlow,
    updateRecoverableField,
    // Actions: 联动
    linkRecoverableToImpairment,
    linkSingleRecoverableToImpairment,
  }
}

export default useI2Impairment
