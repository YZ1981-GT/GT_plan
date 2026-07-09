/**
 * useI1Impairment — I1-12 减值准备测试 + I1-13 可收回金额(DCF)联动
 *
 * 核心功能：
 * 1. I1-12 减值准备测试表（43行×32列×14公式）：
 *    - 逐资产减值测试：账面净值 vs 可收回金额
 *    - 公式：账面净值=原值-摊销-已有减值; 应计提=MAX(净值-可收回,0); 差额=应计提-已计提
 *    - 差额≠0 红色高亮
 * 2. I1-13 可收回金额测试（51行×28列×10公式）：
 *    - DCF模型：预测期现金流(5年) + 折现率 + 终值 + 现值合计
 *    - 公式：PV=Σ(CF_i/(1+r)^i) + TV/(1+r)^n
 *    - 可收回金额=MAX(公允价值-处置费用, DCF使用价值)
 * 3. I1-13 → I1-12 联动：可收回金额自动填入对应行
 * 4. 敏感性分析：折现率±1% / 增长率±0.5%
 *
 * 持久化：
 * - I1-12 rows: "I1-12-rows"
 * - I1-13 rows: "I1-13-rows"
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.6
 * Requirements: 12.1-12.4, 13.1-13.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI1FormData'
import {
  calcDcfPresentValue,
  calcTerminalValue,
  calcRecoverableAmount,
  calcImpairmentAmount,
} from './useI1AmortizationEngine'
import { calcNetValue } from './useI1FormulaEngine'

// ─── Types: I1-12 减值准备测试 ───────────────────────────────────────────────

/** I1-12 减值准备测试行 (Req 12.1) */
export interface I1ImpairmentTestRow {
  rowId: string
  /** 资产名称 */
  name: string
  /** 账面原值 */
  cost: number
  /** 累计摊销 */
  accAmort: number
  /** 已有减值准备 */
  impairmentProvision: number
  /** 账面净值 = 原值 - 摊销 - 已有减值 (Req 12.2) */
  netBookValue: number
  /** 可收回金额（从 I1-13 联动填入，或手工输入）(Req 12.3) */
  recoverableAmount: number
  /** 应计提减值 = MAX(账面净值 - 可收回金额, 0) (Req 12.2) */
  shouldProvision: number
  /** 已计提减值（本期已确认减值金额） */
  alreadyProvided: number
  /** 差额 = 应计提 - 已计提 (Req 12.4 差额≠0红色高亮) */
  difference: number
  /** 审计结论（适当/需补提/需关注） */
  conclusion: string
  /** 是否关联 I1-13 DCF 测试 (Req 12.3) */
  linkedToDcf: boolean
}

// ─── Types: I1-13 可收回金额测试 (DCF) ──────────────────────────────────────

/** DCF 预测期现金流 (5年) */
export const DCF_FORECAST_YEARS = 5

/** I1-13 可收回金额测试行 (Req 13.1-13.3) */
export interface I1RecoverableTestRow {
  rowId: string
  /** 资产名称（与 I1-12 对应） */
  name: string
  /** 预测期现金流数组（5年）(Req 13.1) */
  cashFlows: number[]
  /** 折现率 (如0.08=8%) */
  discountRate: number
  /** 永续增长率 (如0.02=2%) */
  growthRate: number
  /** 终值 = perpetuityCF / (r - g) */
  terminalValue: number
  /** DCF 使用价值 = PV(预测期) + PV(终值) (Req 13.2) */
  valueInUse: number
  /** 公允价值减去处置费用 */
  fairValueLessDisposal: number
  /** 可收回金额 = MAX(公允-处置费, DCF) (Req 13.3) */
  recoverableAmount: number
  /** 各期折现现金流（明细展示） */
  discountedCashFlows: number[]
  /** 终值折现值 */
  discountedTerminalValue: number
}

/** 敏感性分析结果 (Req 13.5) */
export interface SensitivityResult {
  /** 场景描述 */
  scenario: string
  /** 折现率 */
  discountRate: number
  /** 增长率 */
  growthRate: number
  /** 该场景下的 DCF 使用价值 */
  valueInUse: number
  /** 该场景下的可收回金额 */
  recoverableAmount: number
  /** 与基准值差额 */
  differenceFromBase: number
}

/** I1-12 合计行 */
export interface I1ImpairmentSummary {
  totalNetBookValue: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalDifference: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_12_ROWS = 'I1-12-rows'
const ITEM_ID_13_ROWS = 'I1-13-rows'

/** 敏感性分析参数 (Req 13.5) */
const SENSITIVITY_DISCOUNT_DELTA = 0.01  // ±1%
const SENSITIVITY_GROWTH_DELTA = 0.005   // ±0.5%

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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 保存回调（委托 useI1FormData.saveResponse） */
    onSave?: (itemId: string, value: any) => void
  },
) {

  // ─── State: I1-12 减值准备测试 ─────────────────────────────────────────────

  const impairmentRows = ref<I1ImpairmentTestRow[]>([])

  // ─── State: I1-13 可收回金额测试 ───────────────────────────────────────────

  const recoverableRows = ref<I1RecoverableTestRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadImpairmentRows(): void {
    const resp = allResponses.value.get(ITEM_ID_12_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    impairmentRows.value = _safeParseRows<any>(raw).map(_normalizeImpairmentRow)
  }

  function _loadRecoverableRows(): void {
    const resp = allResponses.value.get(ITEM_ID_13_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    recoverableRows.value = _safeParseRows<any>(raw).map(_normalizeRecoverableRow)
  }

  function _normalizeImpairmentRow(raw: any): I1ImpairmentTestRow {
    const cost = _getNum(raw.cost)
    const accAmort = _getNum(raw.accAmort)
    const impairmentProvision = _getNum(raw.impairmentProvision)
    const netBookValue = calcNetValue(cost, accAmort, impairmentProvision)
    const recoverableAmount = _getNum(raw.recoverableAmount)
    const shouldProvision = calcImpairmentAmount(netBookValue, recoverableAmount)
    const alreadyProvided = _getNum(raw.alreadyProvided)
    const difference = shouldProvision - alreadyProvided

    return {
      rowId: raw.rowId ?? _genRowId('imp12'),
      name: raw.name ?? '',
      cost,
      accAmort,
      impairmentProvision,
      netBookValue,
      recoverableAmount,
      shouldProvision,
      alreadyProvided,
      difference,
      conclusion: raw.conclusion ?? '',
      linkedToDcf: raw.linkedToDcf ?? false,
    }
  }

  function _normalizeRecoverableRow(raw: any): I1RecoverableTestRow {
    const cashFlows: number[] = Array.isArray(raw.cashFlows)
      ? raw.cashFlows.slice(0, DCF_FORECAST_YEARS).map(_getNum)
      : new Array(DCF_FORECAST_YEARS).fill(0)
    // Pad to DCF_FORECAST_YEARS
    while (cashFlows.length < DCF_FORECAST_YEARS) {
      cashFlows.push(0)
    }

    const discountRate = _getNum(raw.discountRate)
    const growthRate = _getNum(raw.growthRate)
    const fairValueLessDisposal = _getNum(raw.fairValueLessDisposal)

    // 计算 DCF
    const { terminalValue, valueInUse, recoverableAmount, discountedCashFlows, discountedTerminalValue } =
      _calcDcfResult(cashFlows, discountRate, growthRate, fairValueLessDisposal)

    return {
      rowId: raw.rowId ?? _genRowId('dcf13'),
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

  // ─── DCF Calculation Core (Req 13.2) ───────────────────────────────────────

  /**
   * 完整 DCF 计算结果。
   * PV = Σ(CF_i / (1+r)^i) + TV / (1+r)^n
   * TV = CF_last × (1+g) / (r - g) （Gordon Growth Model）
   * 可收回金额 = MAX(公允-处置费, DCF)
   */
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
    // 各期折现现金流
    const discountedCashFlows: number[] = []
    if (discountRate > 0) {
      for (let i = 0; i < cashFlows.length; i++) {
        discountedCashFlows.push(cashFlows[i] / Math.pow(1 + discountRate, i + 1))
      }
    } else {
      // 折现率无效，不折现
      for (const cf of cashFlows) {
        discountedCashFlows.push(cf)
      }
    }

    // 预测期现值合计
    const pvForecast = calcDcfPresentValue(cashFlows, discountRate)

    // 终值 = 永续现金流 / (r - g)，永续现金流 = 最后一年CF × (1+g)
    const lastCF = cashFlows.length > 0 ? cashFlows[cashFlows.length - 1] : 0
    const perpetuityCF = lastCF * (1 + growthRate)
    const terminalValue = calcTerminalValue(perpetuityCF, discountRate, growthRate)

    // 终值折现到第n年末: TV / (1+r)^n
    const n = cashFlows.length
    const discountedTerminalValue = discountRate > 0 && n > 0
      ? terminalValue / Math.pow(1 + discountRate, n)
      : terminalValue

    // 使用价值 = 预测期现值 + 终值现值
    const valueInUse = pvForecast + discountedTerminalValue

    // 可收回金额 = MAX(公允-处置费, DCF)
    const recoverableAmount = calcRecoverableAmount(fairValueLessDisposal, valueInUse)

    return {
      terminalValue,
      valueInUse,
      recoverableAmount,
      discountedCashFlows,
      discountedTerminalValue,
    }
  }

  // ─── I1-12: Recalculation (Req 12.2) ───────────────────────────────────────

  /**
   * 重算单行 I1-12 公式：
   * - 账面净值 = 原值 - 累计摊销 - 已有减值
   * - 应计提 = MAX(净值 - 可收回金额, 0)
   * - 差额 = 应计提 - 已计提
   */
  function _recalcImpairmentRow(row: I1ImpairmentTestRow): void {
    row.netBookValue = calcNetValue(row.cost, row.accAmort, row.impairmentProvision)
    row.shouldProvision = calcImpairmentAmount(row.netBookValue, row.recoverableAmount)
    row.difference = row.shouldProvision - row.alreadyProvided
  }

  /**
   * 重算所有 I1-12 行。
   */
  function recalcAllImpairment(): void {
    for (const row of impairmentRows.value) {
      _recalcImpairmentRow(row)
    }
    _persistImpairment()
  }

  /**
   * 重算单行 I1-12。
   */
  function recalcImpairmentRow(rowIndex: number): void {
    const row = impairmentRows.value[rowIndex]
    if (!row) return
    _recalcImpairmentRow(row)
    _persistImpairment()
  }

  // ─── I1-13: Recalculation (Req 13.2) ───────────────────────────────────────

  /**
   * 重算单行 I1-13 DCF：
   * - PV = Σ(CF_i/(1+r)^(i+1)) + TV/(1+r)^n
   * - 可收回 = MAX(公允-处置费, DCF)
   */
  function _recalcRecoverableRow(row: I1RecoverableTestRow): void {
    const result = _calcDcfResult(
      row.cashFlows,
      row.discountRate,
      row.growthRate,
      row.fairValueLessDisposal,
    )
    row.terminalValue = result.terminalValue
    row.valueInUse = result.valueInUse
    row.recoverableAmount = result.recoverableAmount
    row.discountedCashFlows = result.discountedCashFlows
    row.discountedTerminalValue = result.discountedTerminalValue
  }

  /**
   * 重算所有 I1-13 行。
   */
  function recalcAllRecoverable(): void {
    for (const row of recoverableRows.value) {
      _recalcRecoverableRow(row)
    }
    _persistRecoverable()
  }

  /**
   * 重算单行 I1-13。
   */
  function recalcRecoverableRow(rowIndex: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    _recalcRecoverableRow(row)
    _persistRecoverable()
  }

  // ─── I1-13 → I1-12 联动 (Req 13.4) ────────────────────────────────────────

  /**
   * 将 I1-13 可收回金额联动填入 I1-12 对应行。
   * 按 name 字段匹配。更新后触发 I1-12 重算。
   */
  function linkRecoverableToImpairment(): void {
    const recoverableMap = new Map<string, number>()
    for (const row of recoverableRows.value) {
      if (row.name) {
        recoverableMap.set(row.name, row.recoverableAmount)
      }
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

    if (changed) {
      _persistImpairment()
    }
  }

  /**
   * 联动单行：I1-13某行重算后自动填入 I1-12 对应行。
   */
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

  // ─── Sensitivity Analysis (Req 13.5) ───────────────────────────────────────

  /**
   * 敏感性分析：折现率±1% / 增长率±0.5%，产出 5 个场景对比。
   * Req 13.5: 提供敏感性分析（折现率±1%/增长率±0.5%对结果影响）
   *
   * 返回 5 行：基准 / r+1% / r-1% / g+0.5% / g-0.5%
   */
  function calcSensitivity(recoverableRowIndex: number): SensitivityResult[] {
    const row = recoverableRows.value[recoverableRowIndex]
    if (!row) return []

    const baseR = row.discountRate
    const baseG = row.growthRate
    const baseFV = row.fairValueLessDisposal
    const cfs = row.cashFlows

    const scenarios: Array<{ label: string; r: number; g: number }> = [
      { label: '基准情景', r: baseR, g: baseG },
      { label: `折现率+1% (${((baseR + SENSITIVITY_DISCOUNT_DELTA) * 100).toFixed(1)}%)`, r: baseR + SENSITIVITY_DISCOUNT_DELTA, g: baseG },
      { label: `折现率-1% (${((baseR - SENSITIVITY_DISCOUNT_DELTA) * 100).toFixed(1)}%)`, r: baseR - SENSITIVITY_DISCOUNT_DELTA, g: baseG },
      { label: `增长率+0.5% (${((baseG + SENSITIVITY_GROWTH_DELTA) * 100).toFixed(2)}%)`, r: baseR, g: baseG + SENSITIVITY_GROWTH_DELTA },
      { label: `增长率-0.5% (${((baseG - SENSITIVITY_GROWTH_DELTA) * 100).toFixed(2)}%)`, r: baseR, g: baseG - SENSITIVITY_GROWTH_DELTA },
    ]

    const baseResult = _calcDcfResult(cfs, baseR, baseG, baseFV)

    return scenarios.map((s) => {
      const result = _calcDcfResult(cfs, s.r, s.g, baseFV)
      return {
        scenario: s.label,
        discountRate: s.r,
        growthRate: s.g,
        valueInUse: result.valueInUse,
        recoverableAmount: result.recoverableAmount,
        differenceFromBase: result.recoverableAmount - baseResult.recoverableAmount,
      }
    })
  }

  // ─── Computed: I1-12 合计行 ─────────────────────────────────────────────────

  /** I1-12 合计行 */
  const impairmentSummary: ComputedRef<I1ImpairmentSummary> = computed(() => {
    let totalNetBookValue = 0
    let totalShouldProvision = 0
    let totalAlreadyProvided = 0
    let totalDifference = 0

    for (const row of impairmentRows.value) {
      totalNetBookValue += row.netBookValue
      totalShouldProvision += row.shouldProvision
      totalAlreadyProvided += row.alreadyProvided
      totalDifference += row.difference
    }

    return { totalNetBookValue, totalShouldProvision, totalAlreadyProvided, totalDifference }
  })

  // ─── Computed: 差额≠0的行（红色高亮用）(Req 12.4) ─────────────────────────

  /**
   * 差额≠0 的行 rowId 集合（供视图红色高亮判断）。
   * Req 12.4: 差额≠0时红色高亮。
   */
  const highlightedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of impairmentRows.value) {
      if (Math.abs(row.difference) > 0.005) {
        ids.add(row.rowId)
      }
    }
    return ids
  })

  // ─── Row Management: I1-12 ─────────────────────────────────────────────────

  /**
   * 添加 I1-12 减值测试行。
   */
  function addImpairmentRow(params: {
    name: string
    cost: number
    accAmort: number
    impairmentProvision?: number
    recoverableAmount?: number
    alreadyProvided?: number
    linkedToDcf?: boolean
  }): I1ImpairmentTestRow {
    const cost = params.cost
    const accAmort = params.accAmort
    const impairmentProvision = params.impairmentProvision ?? 0
    const netBookValue = calcNetValue(cost, accAmort, impairmentProvision)
    const recoverableAmount = params.recoverableAmount ?? 0
    const shouldProvision = calcImpairmentAmount(netBookValue, recoverableAmount)
    const alreadyProvided = params.alreadyProvided ?? 0

    const row: I1ImpairmentTestRow = {
      rowId: _genRowId('imp12'),
      name: params.name,
      cost,
      accAmort,
      impairmentProvision,
      netBookValue,
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

  /**
   * 删除 I1-12 行。
   */
  function removeImpairmentRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= impairmentRows.value.length) return
    impairmentRows.value.splice(rowIndex, 1)
    _persistImpairment()
  }

  /**
   * 更新 I1-12 行的单个字段并重算。
   */
  function updateImpairmentField(
    rowIndex: number,
    field: keyof I1ImpairmentTestRow,
    value: number | string | boolean,
  ): void {
    const row = impairmentRows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    _recalcImpairmentRow(row)
    _persistImpairment()
  }

  // ─── Row Management: I1-13 ─────────────────────────────────────────────────

  /**
   * 添加 I1-13 可收回金额测试行。
   */
  function addRecoverableRow(params: {
    name: string
    cashFlows?: number[]
    discountRate?: number
    growthRate?: number
    fairValueLessDisposal?: number
  }): I1RecoverableTestRow {
    const cashFlows = params.cashFlows?.slice(0, DCF_FORECAST_YEARS) ?? new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = params.discountRate ?? 0.08
    const growthRate = params.growthRate ?? 0.02
    const fairValueLessDisposal = params.fairValueLessDisposal ?? 0

    const result = _calcDcfResult(cashFlows, discountRate, growthRate, fairValueLessDisposal)

    const row: I1RecoverableTestRow = {
      rowId: _genRowId('dcf13'),
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

  /**
   * 删除 I1-13 行。
   */
  function removeRecoverableRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= recoverableRows.value.length) return
    recoverableRows.value.splice(rowIndex, 1)
    _persistRecoverable()
  }

  /**
   * 更新 I1-13 行的现金流数组某年值。
   */
  function updateCashFlow(rowIndex: number, yearIndex: number, value: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row || yearIndex < 0 || yearIndex >= DCF_FORECAST_YEARS) return
    row.cashFlows[yearIndex] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    // 联动 I1-12
    linkSingleRecoverableToImpairment(rowIndex)
  }

  /**
   * 更新 I1-13 行字段（折现率/增长率/公允价值）并重算。
   */
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
    // 联动 I1-12
    linkSingleRecoverableToImpairment(rowIndex)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistImpairment(): void {
    options?.onSave?.(ITEM_ID_12_ROWS, impairmentRows.value)
  }

  function _persistRecoverable(): void {
    options?.onSave?.(ITEM_ID_13_ROWS, recoverableRows.value)
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  /** 导入 I1-12 行（覆盖） */
  function importImpairmentRows(rows: Partial<I1ImpairmentTestRow>[]): void {
    impairmentRows.value = rows.map(_normalizeImpairmentRow)
    recalcAllImpairment()
  }

  /** 导入 I1-13 行（覆盖） */
  function importRecoverableRows(rows: Partial<I1RecoverableTestRow>[]): void {
    recoverableRows.value = rows.map(_normalizeRecoverableRow)
    recalcAllRecoverable()
    linkRecoverableToImpairment()
  }

  /** 导出 I1-12 行 */
  function exportImpairmentRows(): I1ImpairmentTestRow[] {
    return [...impairmentRows.value]
  }

  /** 导出 I1-13 行 */
  function exportRecoverableRows(): I1RecoverableTestRow[] {
    return [...recoverableRows.value]
  }

  // ─── Init: watch allResponses 加载数据 ─────────────────────────────────────

  watch(allResponses, () => {
    _loadImpairmentRows()
    _loadRecoverableRows()
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // ── State ──
    impairmentRows,
    recoverableRows,

    // ── Computed ──
    impairmentSummary,
    highlightedRowIds,

    // ── Constants ──
    DCF_FORECAST_YEARS,

    // ── Actions: I1-12 减值测试 ──
    recalcAllImpairment,
    recalcImpairmentRow,
    addImpairmentRow,
    removeImpairmentRow,
    updateImpairmentField,

    // ── Actions: I1-13 可收回金额(DCF) ──
    recalcAllRecoverable,
    recalcRecoverableRow,
    addRecoverableRow,
    removeRecoverableRow,
    updateCashFlow,
    updateRecoverableField,

    // ── Actions: 联动 ──
    linkRecoverableToImpairment,
    linkSingleRecoverableToImpairment,

    // ── Actions: 敏感性分析 ──
    calcSensitivity,

    // ── Import/Export ──
    importImpairmentRows,
    importRecoverableRows,
    exportImpairmentRows,
    exportRecoverableRows,
  }
}

export default useI1Impairment
