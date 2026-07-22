/**
 * useI2Impairment — I2-15 减值准备测试表 + I2-16 可收回金额测试
 *
 * I2-15 对齐 Excel：迹象① → 是否测试 → ②账面 → ③公允/④DCF → ⑤MAX → ⑥应提 → ⑧=⑥−⑦
 * I2-16 对齐 Excel（复用 I1-13 / CAS8）：
 *   一、公允净额（销售协议→活跃市场→估计 − 处置费用）
 *   二、DCF + WACC/CAPM（默认税前折现率）
 *   三、可收回金额 = MAX(①,②) → 回填 I2-15 ③④
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Requirements: 10.1-10.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI2FormData'
import {
  type I2ImpairmentTestRow,
  type I2ImpairmentSummary,
  type I2ImpPrepValidation,
  emptyI2ImpairmentRow,
  normalizeI2ImpairmentRow,
  recomputeI2ImpairmentRow,
  summarizeI2Impairment,
  validateI2ImpairmentPrep,
  seedRowsFromI2Detail,
  suggestI2ImpairmentConclusion,
  buildI2ImpairmentAdjustmentHint,
  buildI2ImpairmentEventDetail,
} from './i2ImpairmentModel'
import {
  DCF_FORECAST_YEARS,
  defaultFvDisposal,
  defaultWaccParams,
  normalizeFvDisposal,
  normalizeWaccParams,
  calcI2RecoverableResult,
  buildI2ConclusionDraft,
  buildI216SyncChecks,
  validateWaccParams,
  compareI2Wacc,
  buildI2SensitivityNote,
  applyPreferValueInUse,
  type I2FairValueDisposal,
  type I2WaccParams,
  type I216SyncCheck,
  type I2WaccCompareResult,
} from './i2RecoverableModel'

export type { I2ImpairmentTestRow, I2ImpairmentSummary, I2ImpPrepValidation, I2FairValueDisposal, I2WaccParams, I216SyncCheck, I2WaccCompareResult }
export { DCF_FORECAST_YEARS }
export {
  emptyI2ImpairmentRow,
  normalizeI2ImpairmentRow,
  recomputeI2ImpairmentRow,
  summarizeI2Impairment,
  validateI2ImpairmentPrep,
  seedRowsFromI2Detail,
  suggestI2ImpairmentConclusion,
  buildI2ImpairmentAdjustmentHint,
} from './i2ImpairmentModel'

/** I2-16 可收回金额测试行（对齐 Excel 一/二/三节） */
export interface I2RecoverableTestRow {
  rowId: string
  name: string
  bookValue: number
  cashFlows: number[]
  discountRate: number
  growthRate: number
  growthRateBasis: string
  usePreTaxRate: boolean
  fvDisposal: I2FairValueDisposal
  waccParams: I2WaccParams
  terminalValue: number
  valueInUse: number
  fairValueLessDisposal: number
  recoverableAmount: number
  discountedCashFlows: number[]
  discountFactors: number[]
  discountedTerminalValue: number
  pvForecast: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
  /** 开发支出常无可观察市价：仅测使用价值 */
  preferValueInUse: boolean
  preferValueInUseReason: string
  /** 上期 WACC（对比用，小数） */
  priorWacc: number
  /** 行业参考 WACC（对比用，小数） */
  industryWacc: number
}

export interface SensitivityResult {
  scenario: string
  discountRate: number
  growthRate: number
  valueInUse: number
  recoverableAmount: number
  differenceFromBase: number
}

const ITEM_ID_15_ROWS = 'I2-15-rows'
const ITEM_ID_16_DCF_PARAMS = 'I2-16-dcf-params'
const ITEM_ID_DETAIL_ROWS = 'I2-2-rows'

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _genRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParseRows<T>(raw: string | null | undefined | any): T[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw as T[]
  try {
    const parsed = JSON.parse(String(raw))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useI2Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const impairmentRows = ref<I2ImpairmentTestRow[]>([])
  const recoverableRows = ref<I2RecoverableTestRow[]>([])

  function _loadImpairmentRows(): void {
    const resp = allResponses.value.get(ITEM_ID_15_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    impairmentRows.value = _safeParseRows<any>(raw).map(normalizeI2ImpairmentRow)
  }

  function _loadRecoverableRows(): void {
    const resp = allResponses.value.get(ITEM_ID_16_DCF_PARAMS)
    const raw = resp?.remark ?? resp?.conclusion
    recoverableRows.value = _safeParseRows<any>(raw).map(_normalizeRecoverableRow)
  }

  function _calcRowResult(row: Pick<
    I2RecoverableTestRow,
    'cashFlows' | 'discountRate' | 'growthRate' | 'fvDisposal' | 'waccParams' | 'usePreTaxRate' | 'fairValueLessDisposal'
  >) {
    return calcI2RecoverableResult({
      cashFlows: row.cashFlows,
      manualDiscountRate: row.discountRate,
      growthRate: row.growthRate,
      fvDisposal: row.fvDisposal,
      waccParams: row.waccParams,
      usePreTaxRate: row.usePreTaxRate,
      legacyFairValueNet: row.fairValueLessDisposal,
    })
  }

  function _applyCalcToRow(row: I2RecoverableTestRow, calc: ReturnType<typeof calcI2RecoverableResult>): void {
    row.terminalValue = calc.terminalValue
    row.valueInUse = calc.valueInUse
    row.discountedCashFlows = calc.discountedCashFlows
    row.discountFactors = calc.discountFactors
    row.discountedTerminalValue = calc.discountedTerminalValue
    row.pvForecast = calc.pvForecast
    row.fairValueLessDisposal = calc.fairValueLessDisposal
    row.fairValueSource = calc.fairValueSource
    row.disposalTotal = calc.disposalTotal
    row.costOfEquity = calc.costOfEquity
    row.waccAfterTax = calc.waccAfterTax
    row.preTaxDiscountRate = calc.preTaxDiscountRate
    row.effectiveDiscountRate = calc.effectiveDiscountRate
    row.rateInvalid = calc.rateInvalid

    const prefer = applyPreferValueInUse(
      calc.fairValueLessDisposal,
      calc.valueInUse,
      !!row.preferValueInUse,
      row.preferValueInUseReason || '',
    )
    row.recoverableAmount = prefer.recoverableAmount
    row.recoverableSource = prefer.recoverableSource
  }

  function _normalizeRecoverableRow(raw: any): I2RecoverableTestRow {
    const cashFlows: number[] = Array.isArray(raw.cashFlows)
      ? raw.cashFlows.slice(0, DCF_FORECAST_YEARS).map(_getNum)
      : new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const fvDisposal = normalizeFvDisposal(raw.fvDisposal)
    const waccParams = normalizeWaccParams(raw.waccParams)
    const discountRate = _getNum(raw.discountRate) || 0.08
    const growthRate = _getNum(raw.growthRate)
    const usePreTaxRate = raw.usePreTaxRate !== false
    const legacyFairValueNet = _getNum(raw.fairValueLessDisposal)

    const calc = calcI2RecoverableResult({
      cashFlows,
      manualDiscountRate: discountRate,
      growthRate,
      fvDisposal,
      waccParams,
      usePreTaxRate,
      legacyFairValueNet,
    })

    const preferValueInUse = !!raw.preferValueInUse
    const preferValueInUseReason = String(raw.preferValueInUseReason ?? '')
    const prefer = applyPreferValueInUse(
      calc.fairValueLessDisposal,
      calc.valueInUse,
      preferValueInUse,
      preferValueInUseReason,
    )

    return {
      rowId: raw.rowId ?? _genRowId('i2dcf16'),
      name: raw.name ?? '',
      bookValue: _getNum(raw.bookValue),
      cashFlows,
      discountRate,
      growthRate,
      growthRateBasis: String(raw.growthRateBasis ?? ''),
      usePreTaxRate,
      fvDisposal,
      waccParams,
      terminalValue: calc.terminalValue,
      valueInUse: calc.valueInUse,
      fairValueLessDisposal: calc.fairValueLessDisposal,
      recoverableAmount: prefer.recoverableAmount,
      discountedCashFlows: calc.discountedCashFlows,
      discountFactors: calc.discountFactors,
      discountedTerminalValue: calc.discountedTerminalValue,
      pvForecast: calc.pvForecast,
      fairValueSource: calc.fairValueSource,
      disposalTotal: calc.disposalTotal,
      recoverableSource: prefer.recoverableSource,
      costOfEquity: calc.costOfEquity,
      waccAfterTax: calc.waccAfterTax,
      preTaxDiscountRate: calc.preTaxDiscountRate,
      effectiveDiscountRate: calc.effectiveDiscountRate,
      rateInvalid: calc.rateInvalid,
      preferValueInUse,
      preferValueInUseReason,
      priorWacc: _getNum(raw.priorWacc),
      industryWacc: _getNum(raw.industryWacc),
    }
  }

  function _recalcImpairmentRow(row: I2ImpairmentTestRow, refreshConclusion = true): void {
    Object.assign(row, recomputeI2ImpairmentRow(row, { refreshConclusion }))
  }

  function recalcAllImpairment(): void {
    for (const row of impairmentRows.value) _recalcImpairmentRow(row)
    _persistImpairment()
  }

  function _recalcRecoverableRow(row: I2RecoverableTestRow): void {
    _applyCalcToRow(row, _calcRowResult(row))
  }

  function recalcAllRecoverable(): void {
    for (const row of recoverableRows.value) _recalcRecoverableRow(row)
    _persistRecoverable()
    linkRecoverableToImpairment(true)
  }

  function recalcRecoverableRow(rowIndex: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    _recalcRecoverableRow(row)
    _persistRecoverable()
  }

  /** I2-16 → I2-15：回填③公允 + ④DCF，重算⑤⑥⑧ */
  function linkRecoverableToImpairment(onlyLinked = false): { ok: boolean; message: string; count: number } {
    const recoverableMap = new Map<string, I2RecoverableTestRow>()
    for (const row of recoverableRows.value) {
      const key = (row.name || '').trim()
      if (key) recoverableMap.set(key, row)
    }

    let count = 0
    for (const row of impairmentRows.value) {
      const key = (row.name || '').trim()
      if (!key || !row.needTest) continue
      if (onlyLinked && !row.linkedToDcf) continue
      const src = recoverableMap.get(key)
      if (!src) continue

      row.fairValueLessDisposal = src.fairValueLessDisposal
      row.dcfValue = src.valueInUse
      row.linkedToDcf = true
      if (!/I2-16/i.test(row.indexRef || '')) {
        row.indexRef = row.indexRef ? `${row.indexRef};I2-16` : 'I2-16'
      }
      _recalcImpairmentRow(row)
      count++
    }
    if (count > 0) _persistImpairment()
    return {
      ok: count > 0,
      count,
      message: count > 0 ? `已从 I2-16 回填 ${count} 行（③④→⑤）` : '无匹配行可回填（请确认项目名称一致且须测试）',
    }
  }

  function linkSingleRecoverableToImpairment(recoverableRowIndex: number): void {
    const rcRow = recoverableRows.value[recoverableRowIndex]
    if (!rcRow?.name) return
    const key = rcRow.name.trim()
    for (const impRow of impairmentRows.value) {
      if ((impRow.name || '').trim() === key && (impRow.linkedToDcf || impRow.needTest)) {
        impRow.fairValueLessDisposal = rcRow.fairValueLessDisposal
        impRow.dcfValue = rcRow.valueInUse
        impRow.linkedToDcf = true
        if (!/I2-16/i.test(impRow.indexRef || '')) {
          impRow.indexRef = impRow.indexRef ? `${impRow.indexRef};I2-16` : 'I2-16'
        }
        _recalcImpairmentRow(impRow)
      }
    }
    _persistImpairment()
  }

  function seedRecoverableFromImpairment(): { ok: boolean; message: string; count: number } {
    const existing = new Set(recoverableRows.value.map((r) => (r.name || '').trim()).filter(Boolean))
    let count = 0
    for (const row of impairmentRows.value) {
      const name = (row.name || '').trim()
      if (!name || !row.needTest || existing.has(name)) continue
      addRecoverableRow({
        name,
        bookValue: row.bookValue,
        fairValueLessDisposal: row.fairValueLessDisposal,
      })
      row.linkedToDcf = true
      if (!/I2-16/i.test(row.indexRef || '')) {
        row.indexRef = row.indexRef ? `${row.indexRef};I2-16` : 'I2-16'
      }
      existing.add(name)
      count++
    }
    if (count > 0) _persistImpairment()
    return {
      ok: count > 0,
      count,
      message: count > 0
        ? `已从 I2-15 新建 ${count} 项 I2-16 测算`
        : '无可新建项（须先标记减值迹象/须测试，且尚未建组）',
    }
  }

  /** alias：与 I1「从减值表建组」命名对齐 */
  function seedFromImpairment() {
    return seedRecoverableFromImpairment()
  }

  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const resp = allResponses.value.get(ITEM_ID_DETAIL_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    const parsed = _safeParseRows<any>(raw)
    const seeded = seedRowsFromI2Detail(parsed)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I2-2 无明细行可带入' }
    }

    const byName = new Map(impairmentRows.value.map((r) => [(r.name || '').trim(), r]))
    let count = 0
    for (const s of seeded) {
      const key = s.name.trim()
      const prev = byName.get(key)
      if (prev) {
        prev.bookValue = s.bookValue
        prev.alreadyProvided = s.alreadyProvided || prev.alreadyProvided
        prev.sourceDetailRowId = s.sourceDetailRowId
        if (!prev.remark) prev.remark = s.remark
        _recalcImpairmentRow(prev)
        count++
      } else {
        impairmentRows.value.push(s)
        byName.set(key, s)
        count++
      }
    }
    if (count > 0) _persistImpairment()
    return { ok: count > 0, count, message: `已从 I2-2 带入/更新 ${count} 行` }
  }

  const impairmentSummary: ComputedRef<I2ImpairmentSummary> = computed(() =>
    summarizeI2Impairment(impairmentRows.value),
  )

  const prepValidation: ComputedRef<I2ImpPrepValidation> = computed(() =>
    validateI2ImpairmentPrep(impairmentRows.value),
  )

  const syncChecks: ComputedRef<I216SyncCheck[]> = computed(() =>
    buildI216SyncChecks(impairmentRows.value, recoverableRows.value),
  )

  const staleSyncCount = computed(() =>
    syncChecks.value.filter((c) => c.status === 'stale' || c.status === 'missing-i16').length,
  )

  const missingRecoverableRows = computed(() =>
    impairmentRows.value.filter((r) => {
      if (!r.needTest || !r.name.trim()) return false
      const hit = recoverableRows.value.find((x) => (x.name || '').trim() === r.name.trim())
      return !hit || (hit.recoverableAmount <= 0 && r.recoverableAmount <= 0)
    }),
  )

  const highlightedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of impairmentRows.value) {
      if (Math.abs(row.difference) > 0.005) ids.add(row.rowId)
    }
    return ids
  })

  function addImpairmentRow(params: {
    name: string
    bookValue?: number
    recoverableAmount?: number
    fairValueLessDisposal?: number
    dcfValue?: number
    alreadyProvided?: number
    hasIndication?: 'Y' | 'N' | ''
    linkedToDcf?: boolean
  }): I2ImpairmentTestRow {
    const legacyRec = params.recoverableAmount ?? 0
    const row = emptyI2ImpairmentRow({
      name: params.name,
      bookValue: params.bookValue ?? 0,
      fairValueLessDisposal: params.fairValueLessDisposal ?? 0,
      dcfValue: params.dcfValue ?? legacyRec,
      alreadyProvided: params.alreadyProvided ?? 0,
      hasIndication: params.hasIndication ?? '',
      needTest: params.hasIndication === 'Y' || legacyRec > 0,
      linkedToDcf: params.linkedToDcf ?? false,
    })
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

    if (field === 'hasIndication') {
      if (value === 'Y') row.needTest = true
      else if (value === 'N') row.needTest = false
    }
    if (field === 'needTest' && value === true && !row.hasIndication) {
      row.hasIndication = 'Y'
    }
    const keepConclusion = field === 'conclusion' || field === 'remark' || field === 'indexRef' || field === 'name'
    _recalcImpairmentRow(row, !keepConclusion)
    _persistImpairment()
  }

  function addRecoverableRow(params: {
    name: string
    bookValue?: number
    cashFlows?: number[]
    discountRate?: number
    growthRate?: number
    fairValueLessDisposal?: number
  }): I2RecoverableTestRow {
    const cashFlows = params.cashFlows?.slice(0, DCF_FORECAST_YEARS) ?? new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = params.discountRate ?? 0.08
    const growthRate = params.growthRate ?? 0
    const fvDisposal = defaultFvDisposal()
    const waccParams = defaultWaccParams()
    const usePreTaxRate = true
    const legacyFairValueNet = params.fairValueLessDisposal ?? 0

    const calc = calcI2RecoverableResult({
      cashFlows,
      manualDiscountRate: discountRate,
      growthRate,
      fvDisposal,
      waccParams,
      usePreTaxRate,
      legacyFairValueNet,
    })

    const row: I2RecoverableTestRow = {
      rowId: _genRowId('i2dcf16'),
      name: params.name,
      bookValue: params.bookValue ?? 0,
      cashFlows,
      discountRate,
      growthRate,
      growthRateBasis: '',
      usePreTaxRate,
      fvDisposal,
      waccParams,
      terminalValue: calc.terminalValue,
      valueInUse: calc.valueInUse,
      fairValueLessDisposal: calc.fairValueLessDisposal,
      recoverableAmount: calc.recoverableAmount,
      discountedCashFlows: calc.discountedCashFlows,
      discountFactors: calc.discountFactors,
      discountedTerminalValue: calc.discountedTerminalValue,
      pvForecast: calc.pvForecast,
      fairValueSource: calc.fairValueSource,
      disposalTotal: calc.disposalTotal,
      recoverableSource: calc.recoverableSource,
      costOfEquity: calc.costOfEquity,
      waccAfterTax: calc.waccAfterTax,
      preTaxDiscountRate: calc.preTaxDiscountRate,
      effectiveDiscountRate: calc.effectiveDiscountRate,
      rateInvalid: calc.rateInvalid,
      preferValueInUse: false,
      preferValueInUseReason: '',
      priorWacc: 0,
      industryWacc: 0,
    }
    _applyCalcToRow(row, calc)
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
    field: 'discountRate' | 'growthRate' | 'growthRateBasis' | 'usePreTaxRate' | 'bookValue' | 'name'
      | 'preferValueInUse' | 'preferValueInUseReason' | 'priorWacc' | 'industryWacc',
    value: number | string | boolean,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    if (field !== 'name') _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  function updateFvField(
    rowIndex: number,
    field: keyof I2FairValueDisposal,
    value: number | string,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    ;(row.fvDisposal as any)[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  function updateWaccField(
    rowIndex: number,
    field: keyof I2WaccParams,
    value: number,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    row.waccParams[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  function persistRecoverableRow(rowIndex?: number): void {
    if (rowIndex != null) {
      const row = recoverableRows.value[rowIndex]
      if (row) _recalcRecoverableRow(row)
    }
    _persistRecoverable()
  }

  function getWaccWarnings(rowIndex: number): string[] {
    const row = recoverableRows.value[rowIndex]
    if (!row) return []
    const warnings = [...validateWaccParams(row.waccParams)]
    if (row.preferValueInUse && !(row.preferValueInUseReason || '').trim()) {
      warnings.push('已勾选「仅使用价值」，须填写无法可靠确定公允净额的理由')
    }
    warnings.push(...compareI2Wacc({
      currentWacc: row.waccAfterTax || row.effectiveDiscountRate,
      priorWacc: row.priorWacc,
      industryWacc: row.industryWacc,
    }).warnings)
    return warnings
  }

  function getWaccCompare(rowIndex: number): I2WaccCompareResult | null {
    const row = recoverableRows.value[rowIndex]
    if (!row) return null
    return compareI2Wacc({
      currentWacc: row.waccAfterTax || row.effectiveDiscountRate,
      priorWacc: row.priorWacc,
      industryWacc: row.industryWacc,
    })
  }

  function calcSensitivity(recoverableRowIndex: number): SensitivityResult[] {
    const row = recoverableRows.value[recoverableRowIndex]
    if (!row) return []

    const base = _calcRowResult(row)
    const basePrefer = applyPreferValueInUse(
      base.fairValueLessDisposal,
      base.valueInUse,
      !!row.preferValueInUse,
      row.preferValueInUseReason || '',
    )
    const scenarios: Array<{ scenario: string; dr: number; gr: number }> = [
      { scenario: '基准', dr: row.effectiveDiscountRate, gr: row.growthRate },
      { scenario: '折现率 +1%', dr: row.effectiveDiscountRate + 0.01, gr: row.growthRate },
      { scenario: '折现率 −1%', dr: Math.max(0.001, row.effectiveDiscountRate - 0.01), gr: row.growthRate },
      { scenario: '增长率 +0.5%', dr: row.effectiveDiscountRate, gr: row.growthRate + 0.005 },
      { scenario: '增长率 −0.5%', dr: row.effectiveDiscountRate, gr: row.growthRate - 0.005 },
      {
        scenario: '折现率+1% / 增长率−0.5%',
        dr: row.effectiveDiscountRate + 0.01,
        gr: row.growthRate - 0.005,
      },
    ]

    return scenarios.map(({ scenario, dr, gr }) => {
      const result = calcI2RecoverableResult({
        cashFlows: row.cashFlows,
        manualDiscountRate: dr,
        growthRate: gr,
        fvDisposal: row.fvDisposal,
        waccParams: defaultWaccParams(),
        usePreTaxRate: true,
        legacyFairValueNet: row.fairValueLessDisposal,
      })
      const prefer = applyPreferValueInUse(
        result.fairValueLessDisposal,
        result.valueInUse,
        !!row.preferValueInUse,
        row.preferValueInUseReason || '',
      )
      return {
        scenario,
        discountRate: dr,
        growthRate: gr,
        valueInUse: result.valueInUse,
        recoverableAmount: prefer.recoverableAmount,
        differenceFromBase: prefer.recoverableAmount - basePrefer.recoverableAmount,
      }
    })
  }

  function buildConclusionDraft(rowIndex: number): string {
    const row = recoverableRows.value[rowIndex]
    if (!row) return ''
    return buildI2ConclusionDraft({
      assetName: row.name,
      fairValueNet: row.fairValueLessDisposal,
      valueInUse: row.valueInUse,
      recoverableAmount: row.recoverableAmount,
      recoverableSource: row.recoverableSource,
      bookValue: row.bookValue,
      effectiveDiscountRate: row.effectiveDiscountRate,
      growthRate: row.growthRate,
      fromWacc: row.waccAfterTax > 0,
      preferValueInUse: row.preferValueInUse,
      preferValueInUseReason: row.preferValueInUseReason,
    })
  }

  function buildSensitivityNote(rowIndex: number): string {
    const row = recoverableRows.value[rowIndex]
    if (!row) return ''
    return buildI2SensitivityNote({
      assetName: row.name,
      scenarios: calcSensitivity(rowIndex),
    })
  }

  /**
   * 推送本期补提⑧至父级（如 K11 资产减值损失汇总）：
   * dispatch window CustomEvent('impairment:calculated') + 持久化 I2-15-supplement-total
   */
  function publishImpairmentToParent(): { ok: boolean; message: string; supplement: number } {
    const supplement = impairmentSummary.value.totalSupplement
    try {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('impairment:calculated', {
          detail: buildI2ImpairmentEventDetail(impairmentSummary.value),
        }))
      }
    } catch { /* silent */ }
    options?.onSave?.('I2-15-supplement-total', supplement)
    return {
      ok: true,
      supplement,
      message: supplement > 0.005
        ? `已推送本期补提 ${supplement.toFixed(2)} 元`
        : '本期无需补提减值准备，已同步推送状态',
    }
  }

  function _persistImpairment(): void {
    options?.onSave?.(ITEM_ID_15_ROWS, impairmentRows.value)
  }

  function _persistRecoverable(): void {
    options?.onSave?.(ITEM_ID_16_DCF_PARAMS, recoverableRows.value)
  }

  watch(allResponses, () => {
    _loadImpairmentRows()
    _loadRecoverableRows()
  }, { immediate: true })

  void wpId

  return {
    impairmentRows,
    recoverableRows,
    impairmentSummary,
    prepValidation,
    syncChecks,
    staleSyncCount,
    missingRecoverableRows,
    highlightedRowIds,
    DCF_FORECAST_YEARS,
    recalcAllImpairment,
    addImpairmentRow,
    removeImpairmentRow,
    updateImpairmentField,
    seedFromDetail,
    seedRecoverableFromImpairment,
    seedFromImpairment,
    recalcAllRecoverable,
    recalcRecoverableRow,
    addRecoverableRow,
    removeRecoverableRow,
    updateCashFlow,
    updateRecoverableField,
    updateFvField,
    updateWaccField,
    persistRecoverableRow,
    linkRecoverableToImpairment,
    linkSingleRecoverableToImpairment,
    calcSensitivity,
    buildConclusionDraft,
    buildSensitivityNote,
    getWaccWarnings,
    getWaccCompare,
    publishImpairmentToParent,
  }
}

export default useI2Impairment
