/**
 * useK7AmortizationCalc — K7-4 测算表 composable（26行×27列，23公式patterns）
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Task: 3.4
 * Requirements: 4.1-4.7
 *
 * 职责：
 * - 管理测算表行：补助项目/补助总额/相关类型/分摊方法/分摊期总期数/本期期数/
 *   本期应分摊(公式)/累计分摊/期末余额(公式)/企业分摊/差异(公式)/结论
 * - Formulas (use useK7GrantAmortEngine):
 *   calculatedAmort = calcStraightLineAmort(grantTotal, totalPeriods, currentPeriods)
 *   remainingBalance = calcRemainingBalance(grantTotal, accumulatedAmort)
 *   variance = calcAmortVariance(calculatedAmort, enterpriseAmort)
 * - Variance > materiality → red flag
 * - AI assisted conclusion generation (section: amort-conclusion)
 * - Link to K10/K12 via GtIndexChip (grant amort → other income / non-operating income)
 * - JSON打包存储到 "K7-4-rows"
 *
 * CAS16 政府补助分摊测算引擎
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcStraightLineAmort,
  calcRemainingBalance,
  calcAmortVariance,
} from './useK7GrantAmortEngine'
import { calcSubtotal } from './useK7FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K7AmortCalcRow {
  rowId: string
  project: string              // 补助项目名称
  grantTotal: number           // 补助总额
  relatedType: '与资产相关' | '与收益相关'
  amortMethod: string          // 分摊方法（直线法/工作量法/一次性计入）
  totalPeriods: number         // 分摊期总期数（月）
  currentPeriods: number       // 本期期数（月）
  calculatedAmort: number      // 本期应分摊（公式）
  accumulatedAmort: number     // 累计已分摊
  remainingBalance: number     // 期末余额（公式）
  enterpriseAmort: number      // 企业账面分摊
  variance: number             // 差异（公式）
  conclusion: string           // 结论
  /** 差异是否超过重要性水平 → 红色标记 */
  isVarianceExceeded: boolean
}

export interface K7AmortCalcSubtotals {
  grantTotal: number
  calculatedAmort: number
  accumulatedAmort: number
  remainingBalance: number
  enterpriseAmort: number
  variance: number
  count: number
}

export interface UseK7AmortizationCalcParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
  /** 重要性水平（差异超过此值红色标记） */
  materiality?: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K7-4-rows'
const DEFAULT_MATERIALITY = 50000 // 默认5万

const METHOD_OPTIONS = ['直线法', '工作量法', '一次性计入']
const RELATED_TYPE_OPTIONS = ['与资产相关', '与收益相关']
const CONCLUSION_OPTIONS = ['分摊合理', '差异需调整', '方法不当', '待确认']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK7AmortizationCalc(params: UseK7AmortizationCalcParams) {
  const { allResponses, saveResponse, materiality } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const calcRows = ref<K7AmortCalcRow[]>([])

  const materialityValue = computed(() => materiality?.value ?? DEFAULT_MATERIALITY)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { calcRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        calcRows.value = parsed.map(_normalizeRow)
      } else {
        calcRows.value = []
      }
    } catch {
      calcRows.value = []
    }
  }

  function _normalizeRow(raw: any): K7AmortCalcRow {
    const row: K7AmortCalcRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      project: raw.project ?? '',
      grantTotal: Number(raw.grantTotal) || 0,
      relatedType: raw.relatedType ?? '与资产相关',
      amortMethod: raw.amortMethod ?? '直线法',
      totalPeriods: Number(raw.totalPeriods) || 0,
      currentPeriods: Number(raw.currentPeriods) || 0,
      calculatedAmort: 0,
      accumulatedAmort: Number(raw.accumulatedAmort) || 0,
      remainingBalance: 0,
      enterpriseAmort: Number(raw.enterpriseAmort) || 0,
      variance: 0,
      conclusion: raw.conclusion ?? '',
      isVarianceExceeded: false,
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K7AmortCalcRow): void {
    // 本期应分摊=直线法(总额/总期数×本期期数)
    if (row.amortMethod === '一次性计入') {
      // 与收益相关补偿已发生→一次性计入当期损益
      row.calculatedAmort = row.grantTotal
    } else {
      row.calculatedAmort = calcStraightLineAmort(row.grantTotal, row.totalPeriods, row.currentPeriods)
    }
    // 期末余额=总额-累计分摊
    row.remainingBalance = calcRemainingBalance(row.grantTotal, row.accumulatedAmort)
    // 差异=测算分摊-企业分摊
    row.variance = calcAmortVariance(row.calculatedAmort, row.enterpriseAmort)
    // 差异>重要性→红色标记
    row.isVarianceExceeded = Math.abs(row.variance) > materialityValue.value
  }

  function recalcAll(): void {
    for (const row of calcRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K7AmortCalcSubtotals> = computed(() => {
    const r = calcRows.value
    return {
      grantTotal: calcSubtotal(r.map(x => x.grantTotal)),
      calculatedAmort: calcSubtotal(r.map(x => x.calculatedAmort)),
      accumulatedAmort: calcSubtotal(r.map(x => x.accumulatedAmort)),
      remainingBalance: calcSubtotal(r.map(x => x.remainingBalance)),
      enterpriseAmort: calcSubtotal(r.map(x => x.enterpriseAmort)),
      variance: calcSubtotal(r.map(x => x.variance)),
      count: r.length,
    }
  })

  // ─── 超过重要性的项目 (Req 4.6) ───────────────────────────────────────────

  const exceededItems: ComputedRef<K7AmortCalcRow[]> = computed(() =>
    calcRows.value.filter(r => r.isVarianceExceeded),
  )

  const hasExceededVariance: ComputedRef<boolean> = computed(() =>
    exceededItems.value.length > 0,
  )

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = calcRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── 动态行 ────────────────────────────────────────────────────────────────

  function addRow(project: string, relatedType: K7AmortCalcRow['relatedType'] = '与资产相关'): void {
    const newRow: K7AmortCalcRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      project,
      grantTotal: 0,
      relatedType,
      amortMethod: '直线法',
      totalPeriods: 0,
      currentPeriods: 0,
      calculatedAmort: 0,
      accumulatedAmort: 0,
      remainingBalance: 0,
      enterpriseAmort: 0,
      variance: 0,
      conclusion: '',
      isVarianceExceeded: false,
    }
    calcRows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = calcRows.value.findIndex(r => r.rowId === rowId)
    if (idx >= 0) {
      calcRows.value.splice(idx, 1)
      _persist()
    }
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    calcRows.value = data.map(raw => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 统计方法（供 CrossSheet） ─────────────────────────────────────────────

  /** 测算分摊合计（供 K7-2 vs K7-4 交叉验证） */
  function getCalcAmortTotal(): number {
    return subtotals.value.calculatedAmort
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(calcRows.value) })
    // 同步测算分摊合计供CrossSheet computed链使用
    saveResponse('K7-4-calc-amort-total', { remark: String(getCalcAmortTotal()) })
  }

  // ─── Save All ──────────────────────────────────────────────────────────────

  function saveAll(): void {
    _persist()
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    calcRows,
    subtotals,
    exceededItems,
    hasExceededVariance,
    materialityValue,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getCalcAmortTotal,
    saveAll,
    /** 可选项常量 */
    METHOD_OPTIONS,
    RELATED_TYPE_OPTIONS,
    CONCLUSION_OPTIONS,
  }
}
