/**
 * useH1Impairment — H1-14~15 减值 composable
 *
 * 减值迹象6项判断 + 测算表 + DCF模型
 * 敏感性分析矩阵 + 可收回金额MAX选取
 * 从H1-4取数闲置资产列表
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.14
 * Requirements: 13.1-13.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcDcfPresentValue, calcTerminalValue } from './useH1DepreciationEngine'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 减值迹象判断（6项） */
export interface ImpairmentIndication {
  key: string
  description: string
  result: 'Y' | 'N' | 'NA' | ''   // Y=存在迹象 N=不存在 NA=不适用
  explanation: string
}

/** 减值测算行 */
export interface ImpairmentCalcRow {
  rowId: string
  assetGroup: string              // 资产组名称
  bookValue: number               // 账面价值
  fairValueLessDisposal: number   // 公允价值减处置费用
  dcfValue: number                // 预计未来现金流现值(DCF)
  recoverableAmount: number       // 可收回金额（公式MAX）
  impairmentAmount: number        // 减值金额（公式）
  alreadyProvided: number         // 已计提减值
  difference: number              // 差异（公式）
  remark: string
}

/** DCF模型参数 */
export interface DcfModelParams {
  discountRate: number            // 折现率(%)
  forecastPeriod: number          // 预测期(年)
  perpetualGrowthRate: number     // 永续增长率(%)
  cashFlows: number[]             // Year1~YearN自由现金流
  terminalCashFlow: number        // 永续期现金流
}

/** 敏感性分析单元 */
export interface SensitivityCell {
  discountRate: number
  growthRate: number
  recoverableAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_14 = 'H1-14'
const ITEM_PREFIX_15 = 'H1-15'

/** CAS8减值迹象6项 */
const INDICATION_DEFINITIONS: Pick<ImpairmentIndication, 'key' | 'description'>[] = [
  { key: 'market_decline', description: '资产的市价当期大幅度下跌，其跌幅明显高于因时间的推移或者正常使用而预计的下跌' },
  { key: 'tech_change', description: '企业经营所处的经济、技术或者法律等环境以及资产所处的市场在当期或者将在近期发生重大变化' },
  { key: 'rate_increase', description: '市场利率或者其他市场投资报酬率在当期已经提高，从而影响企业计算资产预计未来现金流量现值的折现率' },
  { key: 'obsolescence', description: '有证据表明资产已经陈旧过时或者其实体已经损坏' },
  { key: 'idle_abandoned', description: '资产已经或者将被闲置、终止使用或者计划提前处置' },
  { key: 'underperform', description: '企业内部报告的证据表明资产的经济绩效已经低于或者将低于预期' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Impairment(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetIdleAssets?: Ref<Array<{ name: string; netValue: number }>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  // H1-14
  const indications = ref<ImpairmentIndication[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])

  // H1-15 DCF
  const dcfParams = ref<DcfModelParams>({
    discountRate: 10,
    forecastPeriod: 5,
    perpetualGrowthRate: 2,
    cashFlows: [0, 0, 0, 0, 0],
    terminalCashFlow: 0,
  })

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    // 迹象判断
    const indItem = allResponses.value.get(`${ITEM_PREFIX_14}-indications`)
    if (indItem?.remark) {
      try {
        const parsed = JSON.parse(indItem.remark)
        indications.value = Array.isArray(parsed) ? parsed : _buildDefaultIndications()
      } catch { indications.value = _buildDefaultIndications() }
    } else {
      indications.value = _buildDefaultIndications()
    }

    // 测算表
    const calcItem = allResponses.value.get(`${ITEM_PREFIX_14}-calc-rows`)
    if (calcItem?.remark) {
      try {
        const parsed = JSON.parse(calcItem.remark)
        calcRows.value = Array.isArray(parsed) ? parsed.map(_normalizeCalcRow) : []
      } catch { calcRows.value = [] }
    } else { calcRows.value = [] }

    // DCF参数
    const dcfItem = allResponses.value.get(`${ITEM_PREFIX_15}-dcf-params`)
    if (dcfItem?.remark) {
      try { Object.assign(dcfParams.value, JSON.parse(dcfItem.remark)) } catch { /* */ }
    }

    auditNote.value = _getString(`${ITEM_PREFIX_14}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX_14}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _buildDefaultIndications(): ImpairmentIndication[] {
    return INDICATION_DEFINITIONS.map((def) => ({
      ...def,
      result: '' as const,
      explanation: '',
    }))
  }

  function _normalizeCalcRow(raw: any): ImpairmentCalcRow {
    const bookValue = Number(raw.bookValue) || 0
    const fairVLD = Number(raw.fairValueLessDisposal) || 0
    const dcfVal = Number(raw.dcfValue) || 0
    const recoverable = Math.max(fairVLD, dcfVal)
    const impairment = Math.max(bookValue - recoverable, 0)
    const already = Number(raw.alreadyProvided) || 0
    return {
      rowId: raw.rowId ?? `imp-${Math.random().toString(36).slice(2, 10)}`,
      assetGroup: raw.assetGroup ?? '',
      bookValue,
      fairValueLessDisposal: fairVLD,
      dcfValue: dcfVal,
      recoverableAmount: recoverable,
      impairmentAmount: impairment,
      alreadyProvided: already,
      difference: impairment - already,
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: DCF计算 ─────────────────────────────────────────────────────

  const dcfResult = computed(() => {
    const r = dcfParams.value.discountRate / 100
    const g = dcfParams.value.perpetualGrowthRate / 100
    const cfs = dcfParams.value.cashFlows.filter((v) => v != null)
    const pvCashFlows = calcDcfPresentValue(cfs, r)
    const tv = dcfParams.value.terminalCashFlow > 0
      ? calcTerminalValue(dcfParams.value.terminalCashFlow, r, g)
      : 0
    // 终值折现
    const tvDiscounted = tv / Math.pow(1 + r, cfs.length)
    return {
      pvCashFlows,
      terminalValue: tv,
      terminalValueDiscounted: tvDiscounted,
      totalPV: pvCashFlows + tvDiscounted,
    }
  })

  // ─── Computed: 敏感性分析矩阵 ─────────────────────────────────────────────

  const sensitivityMatrix = computed<SensitivityCell[]>(() => {
    const baseRate = dcfParams.value.discountRate / 100
    const baseGrowth = dcfParams.value.perpetualGrowthRate / 100
    const cfs = dcfParams.value.cashFlows
    const termCF = dcfParams.value.terminalCashFlow
    const results: SensitivityCell[] = []

    const rateOffsets = [-0.01, 0, 0.01]
    const growthOffsets = [-0.005, 0, 0.005]

    for (const rOff of rateOffsets) {
      for (const gOff of growthOffsets) {
        const r = baseRate + rOff
        const g = baseGrowth + gOff
        if (r <= g || r <= 0) { results.push({ discountRate: r * 100, growthRate: g * 100, recoverableAmount: 0 }); continue }
        const pv = calcDcfPresentValue(cfs, r)
        const tv = termCF > 0 ? calcTerminalValue(termCF, r, g) / Math.pow(1 + r, cfs.length) : 0
        results.push({
          discountRate: r * 100,
          growthRate: g * 100,
          recoverableAmount: pv + tv,
        })
      }
    }
    return results
  })

  /** 是否有减值迹象 */
  const hasIndication = computed(() =>
    indications.value.some((ind) => ind.result === 'Y'),
  )

  /** 需计提减值的行 */
  const rowsNeedingImpairment = computed(() =>
    calcRows.value.filter((r) => r.impairmentAmount > 0 && r.difference > 0.01),
  )

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function updateIndication(key: string, field: keyof ImpairmentIndication, value: any): void {
    const ind = indications.value.find((i) => i.key === key)
    if (!ind) return
    ;(ind as any)[field] = value
    _persistIndications()
  }

  function updateCalcRow(rowId: string, field: keyof ImpairmentCalcRow, value: any): void {
    const row = calcRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算公式列
    row.recoverableAmount = Math.max(row.fairValueLessDisposal, row.dcfValue)
    row.impairmentAmount = Math.max(row.bookValue - row.recoverableAmount, 0)
    row.difference = row.impairmentAmount - row.alreadyProvided
    _persistCalcRows()
  }

  function addCalcRow(assetGroup: string): void {
    const newRow: ImpairmentCalcRow = {
      rowId: `imp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      assetGroup,
      bookValue: 0, fairValueLessDisposal: 0, dcfValue: 0,
      recoverableAmount: 0, impairmentAmount: 0, alreadyProvided: 0,
      difference: 0, remark: '',
    }
    calcRows.value.push(newRow)
    _persistCalcRows()
  }

  function removeCalcRow(rowId: string): void {
    const idx = calcRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      calcRows.value.splice(idx, 1)
      _persistCalcRows()
    }
  }

  function updateDcfParams(params: Partial<DcfModelParams>): void {
    Object.assign(dcfParams.value, params)
    options?.onSave?.(`${ITEM_PREFIX_15}-dcf-params`, dcfParams.value)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistIndications(): void {
    options?.onSave?.(`${ITEM_PREFIX_14}-indications`, indications.value)
  }

  function _persistCalcRows(): void {
    options?.onSave?.(`${ITEM_PREFIX_14}-calc-rows`, calcRows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_14}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX_14}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    indications,
    calcRows,
    dcfParams,
    auditNote,
    auditConclusion,
    // Computed
    dcfResult,
    sensitivityMatrix,
    hasIndication,
    rowsNeedingImpairment,
    // Actions
    updateIndication,
    updateCalcRow,
    addCalcRow,
    removeCalcRow,
    updateDcfParams,
    saveNote,
    saveConclusion,
    // Constants
    INDICATION_DEFINITIONS,
  }
}

export default useH1Impairment
