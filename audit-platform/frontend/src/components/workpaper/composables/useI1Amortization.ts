/**
 * useI1Amortization — I1-10/I1-11 摊销测算分支选择器 + 摊销矩阵计算
 *
 * 核心功能：
 * 1. 分支选择器状态：amortBranch ref ('noImpair' | 'withImpair')
 *    - 'noImpair' → I1-10 不含减值（剩余年限法, 30 公式）
 *    - 'withImpair' → I1-11 含减值（63 公式）
 * 2. 摊销矩阵：每资产每月摊销额横向矩阵（28列宽表）
 * 3. 月摊销计算：调用 useI1AmortizationEngine 纯函数
 * 4. 减值月重置：含减值版本在减值发生月重新计算剩余摊销基数
 * 5. 期间合计：per-asset period totals 供 I1-9 摊销分配联动
 * 6. 资产行管理：从 I1-2 明细取资产参数（名称/原值/残值/使用寿命）
 * 7. 持久化：rows JSON → checklist_responses "I1-10-rows" 或 "I1-11-rows"
 * 8. 合计行：底部 subtotal 联动 I1-9
 *
 * 科目方向：
 * - 1702 累计摊销（贷方/备抵类）：月摊销额为贷方发生
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.5
 * Requirements: 11.1-11.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

import { exportMultiSheetData, readSheetObjects } from '@/composables/useExcelIO'
import type { ChecklistItem } from './useI1FormData'
import {
  calcRemainingLifeAmort,
  calcRemainingLifeAmortTest,
  calcAmortWithImpairment,
  calcAmortWithImpairmentTest,
} from './useI1AmortizationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 摊销分支类型 */
export type AmortBranch = 'noImpair' | 'withImpair'

/** 分支选择器选项（供 el-segmented 使用） */
export interface AmortBranchOption {
  label: string
  value: AmortBranch
}

/** 摊销矩阵行：I1-10 矩阵 + I1-11 源表分段字段 */
export interface I1AmortizationRow {
  rowId: string
  /** 资产分类（土地使用权/专利权/软件等） */
  category: string
  /** 资产名称（来自 I1-2） */
  name: string
  /** 原值 */
  cost: number
  /** 预计残值 */
  salvage: number
  /** 累计摊销期初 / 账面累计摊销 */
  accAmortBegin: number
  /** 账面累计摊销期末（差异核对用，默认=accAmortBegin） */
  bookAccAmortEnd: number
  /** 减值准备（仅 withImpair 分支使用） */
  impairment: number
  /** 开始使用日期 YYYY-MM-DD */
  startDate: string
  /** 使用寿命（年）— I1-11 源表输入 */
  usefulLifeYears: number
  /** 账面月摊销额 */
  bookMonthly: number
  /** 账面本期摊销额（I1-10 源列 N，优先于 bookMonthly×月数） */
  bookPeriodAmort: number
  /** 减值计提日期 YYYY-MM-DD（行级，优于模板全局日） */
  impairmentDate: string
  /** 使用寿命总月数 */
  usefulLifeMonths: number
  /** 已使用月数 */
  usedMonths: number
  /** 剩余月数 = usefulLifeMonths - usedMonths */
  remainingMonths: number
  /** 期初净值 F = 原值 − 残值 − 累计摊销 − 减值 */
  beginNbv: number
  /** 测算到期日 */
  fullAmortDate: string
  /** 已摊销月份 */
  monthsAmortized: number
  /** 截止减值日累计摊销月份 */
  monthsToImpairment: number
  /** 本期摊销月份 */
  periodMonths: number
  /** 本期减值前月数 */
  monthsBeforeImpairment: number
  /** 本期减值后月数 */
  monthsAfterImpairment: number
  /** 减值前月摊销额 */
  preMonthly: number
  /** 减值时测算累计摊销 */
  accAmortAtImpairment: number
  /** 减值后月摊销额 */
  postMonthly: number
  /** 月摊销额差异 = 账面月摊销 − 减值后月摊销 */
  monthlyDiff: number
  /** 本期摊销额差异 = 测算本期 − 账面本期（I1-10 源列 O） */
  periodDiff: number
  /** 累计摊销(测算) */
  calcAccAmort: number
  /** 累计摊销差异 = 账面 − 测算 */
  accAmortDiff: number
  /** 减值发生月（1-based 月索引，0=无减值）：兼容旧矩阵路径 */
  impairmentMonth: number
  /** 减值发生后新增的减值金额 */
  impairmentAmountAtMonth: number
  /** 月摊销额矩阵（最多28列，对应审计期间月份） */
  monthlyAmort: number[]
  /** 本期摊销合计 = sum(monthlyAmort) 或 T=Q×O+S×P */
  periodAmortization: number
  /** 当前月摊销额（最终计算值） */
  monthlyAmortAmount: number
}

/** 合计行结构 */
export interface I1AmortizationSummary {
  /** 各月合计（28列） */
  monthlyTotals: number[]
  /** 本期摊销总合计 */
  periodTotal: number
}

/** I1-10/11 ↔ I1-1 本期计提 / I1-9 分配合计勾稽 */
export interface I1AmortReconcileResult {
  adjudicatedProvision: number
  periodAmortTotal: number
  allocTotal: number
  vsAdjDiff: number
  vsAllocDiff: number
  matchedAdj: boolean
  matchedAlloc: boolean
}

/** 从 I1-2 提取的资产参数（用于初始化/同步行） */
export interface I1AssetParams {
  rowId: string
  name: string
  category?: string
  cost: number
  salvageRate: number
  usefulLifeMonths: number
  accAmortBegin: number
  /** 账面累计摊销期末（优先用于差异核对） */
  accAmortEnd?: number
  impairmentEnd: number
  acquisitionDate?: string
  /** 本期账面摊销额 → 推算账面月摊销 */
  amortProvision?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 摊销矩阵列数（月数），28列宽表 */
const MATRIX_COLUMNS = 28

/** 分支选项（供 el-segmented） */
export const AMORT_BRANCH_OPTIONS: AmortBranchOption[] = [
  { label: '不含减值（I1-10）', value: 'noImpair' },
  { label: '含减值（I1-11）', value: 'withImpair' },
]

/** checklist_responses 持久化 key */
const ITEM_ID_NO_IMPAIR = 'I1-10-rows'
const ITEM_ID_WITH_IMPAIR = 'I1-11-rows'
const ITEM_ID_BRANCH = 'I1-amort-branch'
/** I1-10/I1-11 共用审计期间（新键；写时双写旧键兼容） */
const ITEM_ID_PERIOD = 'I1-amort-period'
const ITEM_ID_PERIOD_LEGACY = 'I1-11-period'
const ITEM_ID_PERIOD_TOTAL_NO = 'I1-10-period-amort-total'
const ITEM_ID_PERIOD_TOTAL_WITH = 'I1-11-period-amort-total'
const I1_ADJ_AMORT_PROVISION_KEYS = [
  'I1-adj-amort-increase-total',
  'I1-1-amort-provision',
] as const
const I1_ALLOC_TOTALS_KEY = 'I1-9-alloc-totals'
const RECONCILE_TOLERANCE = 0.01

function _round2(n: number): number {
  return Math.round((n || 0) * 100) / 100
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _genRowId(): string {
  return `amort-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Amortization(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 保存回调（委托 useI1FormData.saveResponse） */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 分支选择器：'noImpair' (I1-10) | 'withImpair' (I1-11) */
  const amortBranch = ref<AmortBranch>('noImpair')

  /** I1-10 不含减值行数据 */
  const rowsNoImpair = ref<I1AmortizationRow[]>([])

  /** I1-11 含减值行数据 */
  const rowsWithImpair = ref<I1AmortizationRow[]>([])

  /** I1-11 审计期间（对齐源表 $B$8 / $D$8） */
  const periodBegin = ref<string>('')
  const periodEnd = ref<string>('')

  // ─── Derived: 当前分支行 ───────────────────────────────────────────────────

  /** 当前分支对应的行数据 */
  const currentRows = computed<I1AmortizationRow[]>(() => {
    return amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
  })

  /** 当前分支的 item_id */
  const currentItemId = computed<string>(() => {
    return amortBranch.value === 'noImpair' ? ITEM_ID_NO_IMPAIR : ITEM_ID_WITH_IMPAIR
  })

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadBranch(): void {
    const item = allResponses.value.get(ITEM_ID_BRANCH)
    const raw = item?.remark ?? item?.conclusion
    if (raw === 'withImpair' || raw === 'noImpair') {
      amortBranch.value = raw
    }
  }

  function _parsePeriodRaw(raw: unknown): { begin?: string; end?: string } | null {
    if (!raw) return null
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!parsed || typeof parsed !== 'object') return null
      return {
        begin: parsed.periodBegin ? String(parsed.periodBegin) : undefined,
        end: parsed.periodEnd ? String(parsed.periodEnd) : undefined,
      }
    } catch {
      return null
    }
  }

  function _loadPeriod(): void {
    // 优先新键 I1-amort-period，回退旧键 I1-11-period
    const primary = allResponses.value.get(ITEM_ID_PERIOD)
    const legacy = allResponses.value.get(ITEM_ID_PERIOD_LEGACY)
    const parsed =
      _parsePeriodRaw(primary?.remark ?? primary?.conclusion)
      ?? _parsePeriodRaw(legacy?.remark ?? legacy?.conclusion)
    if (!parsed) return
    if (parsed.begin) periodBegin.value = parsed.begin
    if (parsed.end) periodEnd.value = parsed.end
  }

  function _loadRows(): void {
    // Load I1-10 rows
    const resp10 = allResponses.value.get(ITEM_ID_NO_IMPAIR)
    const raw10 = resp10?.remark ?? resp10?.conclusion
    rowsNoImpair.value = _parseRows(raw10)

    // Load I1-11 rows
    const resp11 = allResponses.value.get(ITEM_ID_WITH_IMPAIR)
    const raw11 = resp11?.remark ?? resp11?.conclusion
    rowsWithImpair.value = _parseRows(raw11)
  }

  function _parseRows(raw: string | null | undefined): I1AmortizationRow[] {
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map(_normalizeRow)
    } catch {
      return []
    }
  }

  function _normalizeRow(raw: any): I1AmortizationRow {
    const monthlyAmort: number[] = Array.isArray(raw.monthlyAmort)
      ? raw.monthlyAmort.slice(0, MATRIX_COLUMNS).map(_getNum)
      : new Array(MATRIX_COLUMNS).fill(0)

    // Pad to MATRIX_COLUMNS if shorter
    while (monthlyAmort.length < MATRIX_COLUMNS) {
      monthlyAmort.push(0)
    }

    const periodAmortization = monthlyAmort.reduce((sum, v) => sum + v, 0)
    const usefulLifeMonths = _getNum(raw.usefulLifeMonths)
    const usefulLifeYears = _getNum(raw.usefulLifeYears)
      || (usefulLifeMonths > 0 ? Math.round((usefulLifeMonths / 12) * 100) / 100 : 0)

    return {
      rowId: raw.rowId ?? _genRowId(),
      category: raw.category ?? '',
      name: raw.name ?? '',
      cost: _getNum(raw.cost),
      salvage: _getNum(raw.salvage),
      accAmortBegin: _getNum(raw.accAmortBegin),
      bookAccAmortEnd: _getNum(raw.bookAccAmortEnd) || _getNum(raw.accAmortBegin),
      impairment: _getNum(raw.impairment),
      startDate: raw.startDate ?? '',
      usefulLifeYears,
      bookMonthly: _getNum(raw.bookMonthly),
      bookPeriodAmort: _getNum(raw.bookPeriodAmort)
        || (_getNum(raw.bookMonthly) > 0 ? 0 : _getNum(raw.amortProvision)),
      impairmentDate: raw.impairmentDate ?? '',
      usefulLifeMonths,
      usedMonths: _getNum(raw.usedMonths),
      remainingMonths: _getNum(raw.remainingMonths),
      beginNbv: _getNum(raw.beginNbv),
      fullAmortDate: raw.fullAmortDate ?? '',
      monthsAmortized: _getNum(raw.monthsAmortized),
      monthsToImpairment: _getNum(raw.monthsToImpairment),
      periodMonths: _getNum(raw.periodMonths),
      monthsBeforeImpairment: _getNum(raw.monthsBeforeImpairment),
      monthsAfterImpairment: _getNum(raw.monthsAfterImpairment),
      preMonthly: _getNum(raw.preMonthly),
      accAmortAtImpairment: _getNum(raw.accAmortAtImpairment),
      postMonthly: _getNum(raw.postMonthly),
      monthlyDiff: _getNum(raw.monthlyDiff),
      periodDiff: _getNum(raw.periodDiff),
      calcAccAmort: _getNum(raw.calcAccAmort),
      accAmortDiff: _getNum(raw.accAmortDiff),
      impairmentMonth: _getNum(raw.impairmentMonth),
      impairmentAmountAtMonth: _getNum(raw.impairmentAmountAtMonth),
      monthlyAmort,
      periodAmortization: _getNum(raw.periodAmortization) || periodAmortization,
      monthlyAmortAmount: _getNum(raw.monthlyAmortAmount),
    }
  }

  // ─── Branch Switch (Req 11.1) ──────────────────────────────────────────────

  /**
   * 切换摊销分支。
   * @param persist 是否写入 checklist（默认 true）；组件 mount 初始化应传 false，避免覆盖用户分支偏好
   */
  function switchBranch(branch: AmortBranch, persist = true): void {
    amortBranch.value = branch
    if (persist) options?.onSave?.(ITEM_ID_BRANCH, branch)
  }

  // ─── Amortization Matrix Calculation ───────────────────────────────────────

  /**
   * 计算单行摊销（不含减值版本 — I1-10）。
   * 优先走源表日期剩余年限法；无日期时回退手工剩余月数路径。
   *
   * 源表：K=F/J，M=K×本期月数，O=M−N；本实现改进「本期月数」为期间四分支。
   */
  function _calcMatrixNoImpair(row: I1AmortizationRow): void {
    const {
      cost, salvage, accAmortBegin, impairment, startDate, usefulLifeYears,
      usefulLifeMonths, bookPeriodAmort, bookMonthly, bookAccAmortEnd, remainingMonths,
    } = row

    const bookPeriod = bookPeriodAmort > 0
      ? bookPeriodAmort
      : (bookMonthly > 0 ? round2Local(bookMonthly * 12) : 0)

    // ── 主路径：有开始日期或已填使用寿命 → 对齐源表 I1-10 ──────────────────
    if (startDate || usefulLifeYears > 0 || usefulLifeMonths > 0) {
      const result = calcRemainingLifeAmortTest({
        cost,
        salvage,
        accAmortBegin,
        impairmentBegin: impairment > 0 ? impairment : 0,
        usefulLifeYears: usefulLifeYears > 0 ? usefulLifeYears : usefulLifeMonths / 12,
        startDate: startDate || undefined,
        periodBegin: periodBegin.value || undefined,
        periodEnd: periodEnd.value || undefined,
        bookPeriodAmort: bookPeriod,
        bookAccAmortEnd: bookAccAmortEnd || accAmortBegin,
      })

      row.beginNbv = result.beginNbv
      row.usefulLifeMonths = result.lifeMonths || usefulLifeMonths
      row.fullAmortDate = result.fullAmortDate
      row.usedMonths = result.monthsElapsedAtBegin
      row.monthsAmortized = result.monthsElapsedAtBegin + result.periodMonths
      row.remainingMonths = result.remainingMonths
      row.periodMonths = result.periodMonths
      row.monthlyAmortAmount = result.monthlyAmort
      row.periodAmortization = result.periodAmortization
      row.periodDiff = result.periodDiff
      row.calcAccAmort = result.calcAccAmort
      row.accAmortDiff = result.accAmortDiff
      row.monthlyDiff = result.periodMonths > 0
        ? round2Local(bookMonthly - result.monthlyAmort)
        : round2Local((bookPeriod / 12) - result.monthlyAmort)

      const matrix: number[] = new Array(MATRIX_COLUMNS).fill(0)
      const fill = Math.min(result.periodMonths, MATRIX_COLUMNS)
      for (let i = 0; i < fill; i++) matrix[i] = result.monthlyAmort
      row.monthlyAmort = matrix
      return
    }

    // ── 回退：仅手工剩余月数（无寿命/日期）────────────────────────────────
    row.beginNbv = round2Local(cost - salvage - accAmortBegin - (impairment || 0))
    if (remainingMonths <= 0 || cost <= 0) {
      row.monthlyAmort = new Array(MATRIX_COLUMNS).fill(0)
      row.periodAmortization = 0
      row.monthlyAmortAmount = 0
      row.periodMonths = 0
      row.periodDiff = round2Local(0 - bookPeriod)
      row.calcAccAmort = round2Local(accAmortBegin)
      row.accAmortDiff = round2Local((bookAccAmortEnd || accAmortBegin) - accAmortBegin)
      return
    }

    const monthlyAmount = calcRemainingLifeAmort(cost, salvage, accAmortBegin, impairment || 0, remainingMonths)
    const periodMonths = Math.min(12, remainingMonths)
    row.monthlyAmortAmount = monthlyAmount
    row.periodMonths = periodMonths
    row.periodAmortization = round2Local(monthlyAmount * periodMonths)
    row.periodDiff = round2Local(row.periodAmortization - bookPeriod)
    row.calcAccAmort = round2Local(accAmortBegin + row.periodAmortization)
    row.accAmortDiff = round2Local((bookAccAmortEnd || accAmortBegin) - row.calcAccAmort)

    const matrix: number[] = []
    for (let i = 0; i < MATRIX_COLUMNS; i++) {
      matrix.push(i < periodMonths ? monthlyAmount : 0)
    }
    row.monthlyAmort = matrix
  }

  /**
   * 计算单行摊销（含减值版本 — I1-11）。
   * 优先走源表日期分段测算；无日期时回退到旧「减值发生月」矩阵路径。
   */
  function _calcMatrixWithImpair(row: I1AmortizationRow): void {
    const {
      cost, salvage, impairment, startDate, usefulLifeYears,
      bookMonthly, bookAccAmortEnd, impairmentDate,
      remainingMonths, impairmentMonth, impairmentAmountAtMonth, usefulLifeMonths,
    } = row

    // ── 主路径：有开始日期 → 对齐源表 I1-11 ────────────────────────────────
    if (startDate && (usefulLifeYears > 0 || usefulLifeMonths > 0)) {
      const result = calcAmortWithImpairmentTest({
        cost,
        salvage,
        usefulLifeYears: usefulLifeYears > 0 ? usefulLifeYears : usefulLifeMonths / 12,
        startDate,
        periodBegin: periodBegin.value || undefined,
        periodEnd: periodEnd.value || undefined,
        impairmentDate: impairmentDate || undefined,
        impairmentAmount: impairment > 0 ? impairment : impairmentAmountAtMonth,
        bookMonthly,
        bookAccAmortEnd: bookAccAmortEnd || row.accAmortBegin,
      })

      row.usefulLifeMonths = result.lifeMonths
      row.fullAmortDate = result.fullAmortDate
      row.monthsAmortized = result.monthsAmortized
      row.remainingMonths = result.remainingMonths
      row.monthsToImpairment = result.monthsToImpairment
      row.periodMonths = result.periodMonths
      row.monthsBeforeImpairment = result.monthsBeforeImpairment
      row.monthsAfterImpairment = result.monthsAfterImpairment
      row.preMonthly = result.preMonthly
      row.accAmortAtImpairment = result.accAmortAtImpairment
      row.postMonthly = result.postMonthly
      row.periodAmortization = result.periodAmortization
      row.monthlyDiff = result.monthlyDiff
      row.calcAccAmort = result.calcAccAmort
      row.accAmortDiff = result.accAmortDiff
      row.monthlyAmortAmount = result.postMonthly || result.preMonthly

      // 兼容：按减值前/后月数填充矩阵前若干列（供旧视图/合计）
      const matrix: number[] = new Array(MATRIX_COLUMNS).fill(0)
      for (let i = 0; i < MATRIX_COLUMNS; i++) {
        if (i < result.monthsBeforeImpairment) matrix[i] = result.preMonthly
        else if (i < result.monthsBeforeImpairment + result.monthsAfterImpairment) matrix[i] = result.postMonthly
      }
      row.monthlyAmort = matrix
      return
    }

    // ── 回退：旧矩阵路径（无日期） ─────────────────────────────────────────
    if (remainingMonths <= 0 || cost <= 0) {
      row.monthlyAmort = new Array(MATRIX_COLUMNS).fill(0)
      row.periodAmortization = 0
      row.monthlyAmortAmount = 0
      row.preMonthly = 0
      row.postMonthly = 0
      return
    }

    const matrix: number[] = []
    let accAmortCumulative = row.accAmortBegin
    let currentImpairment = impairment - impairmentAmountAtMonth
    let currentRemaining = remainingMonths
    let monthlyAmount = 0
    const effectiveImpairMonth = impairmentMonth > 0 ? impairmentMonth : MATRIX_COLUMNS + 1
    let monthsBefore = 0
    let monthsAfter = 0
    let preMonthly = 0
    let postMonthly = 0
    let accAtImp = 0

    for (let m = 0; m < MATRIX_COLUMNS; m++) {
      if (currentRemaining <= 0) {
        matrix.push(0)
        continue
      }

      if (m + 1 === effectiveImpairMonth) {
        currentImpairment += impairmentAmountAtMonth
        monthlyAmount = calcAmortWithImpairment(
          cost, salvage, accAmortCumulative, currentImpairment, currentRemaining,
        )
        postMonthly = monthlyAmount
        accAtImp = accAmortCumulative
        monthsAfter++
      } else if (m + 1 < effectiveImpairMonth) {
        monthlyAmount = calcRemainingLifeAmort(
          cost, salvage, accAmortCumulative, currentImpairment, currentRemaining,
        )
        if (preMonthly === 0) preMonthly = monthlyAmount
        monthsBefore++
      } else {
        monthsAfter++
      }

      matrix.push(monthlyAmount)
      accAmortCumulative += monthlyAmount
      currentRemaining--
    }

    row.monthlyAmort = matrix
    row.monthlyAmortAmount = monthlyAmount
    row.periodAmortization = matrix.reduce((sum, v) => sum + v, 0)
    row.preMonthly = preMonthly
    row.postMonthly = postMonthly || monthlyAmount
    row.accAmortAtImpairment = accAtImp
    row.monthsBeforeImpairment = monthsBefore
    row.monthsAfterImpairment = monthsAfter
    row.periodMonths = monthsBefore + monthsAfter
    row.monthlyDiff = round2Local(bookMonthly - (postMonthly || monthlyAmount))
    row.calcAccAmort = round2Local(accAmortCumulative)
    row.accAmortDiff = round2Local((bookAccAmortEnd || row.accAmortBegin) - accAmortCumulative)
  }

  function round2Local(n: number): number {
    return Math.round((n || 0) * 100) / 100
  }

  /**
   * 重算当前分支所有行的摊销矩阵。
   */
  function recalcAll(): void {
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    const calcFn = amortBranch.value === 'noImpair' ? _calcMatrixNoImpair : _calcMatrixWithImpair

    for (const row of rows) {
      calcFn(row)
    }

    _persist()
  }

  /**
   * 重算单行摊销矩阵（编辑某行参数后调用）。
   */
  function recalcRow(rowIndex: number): void {
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    const row = rows[rowIndex]
    if (!row) return

    if (amortBranch.value === 'noImpair') {
      _calcMatrixNoImpair(row)
    } else {
      _calcMatrixWithImpair(row)
    }

    _persist()
  }

  // ─── Computed: 合计行（Req 11.7 底部合计联动I1-9）─────────────────────────

  /**
   * 合计行：各月合计 + 本期摊销总合计。
   * Req 11.7: 底部合计行联动 I1-9 摊销分配。
   */
  const summaryRow: ComputedRef<I1AmortizationSummary> = computed(() => {
    const rows = currentRows.value
    const monthlyTotals = new Array(MATRIX_COLUMNS).fill(0)
    let periodTotal = 0

    for (const row of rows) {
      for (let m = 0; m < MATRIX_COLUMNS; m++) {
        monthlyTotals[m] += row.monthlyAmort[m] ?? 0
      }
      periodTotal += row.periodAmortization
    }

    return { monthlyTotals, periodTotal }
  })

  // ─── Computed: per-asset period totals (供 I1-9 摊销分配使用) ───────────────

  /**
   * 按资产名称聚合本期摊销额，供 I1-9 摊销分配表读取。
   * Req 11.7: 合计行联动I1-9摊销分配。
   */
  const assetPeriodTotals: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    for (const row of currentRows.value) {
      const key = row.name || '未命名'
      result[key] = (result[key] ?? 0) + row.periodAmortization
    }
    return result
  })

  function _readNumKey(...keys: string[]): number {
    for (const key of keys) {
      const item = allResponses.value.get(key)
      const raw = item?.remark ?? item?.conclusion
      if (raw == null || raw === '') continue
      const n = Number(raw)
      if (Number.isFinite(n)) return n
    }
    return 0
  }

  function _readAllocSum(): number {
    const item = allResponses.value.get(I1_ALLOC_TOTALS_KEY)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return 0
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      const n = Number(parsed?.allocSum)
      return Number.isFinite(n) ? n : 0
    } catch {
      return 0
    }
  }

  /** 本期测算合计 vs I1-1 摊销本期增加 / I1-9 分配合计 */
  const amortReconcile: ComputedRef<I1AmortReconcileResult> = computed(() => {
    const periodAmortTotal = _round2(summaryRow.value.periodTotal)
    const adjudicatedProvision = _round2(_readNumKey(...I1_ADJ_AMORT_PROVISION_KEYS))
    const allocTotal = _round2(_readAllocSum())
    const vsAdjDiff = _round2(periodAmortTotal - adjudicatedProvision)
    const vsAllocDiff = _round2(allocTotal - periodAmortTotal)
    const matchedAdj =
      adjudicatedProvision === 0
        ? Math.abs(periodAmortTotal) < RECONCILE_TOLERANCE
        : Math.abs(vsAdjDiff) <= RECONCILE_TOLERANCE
    const matchedAlloc =
      allocTotal === 0
        ? true
        : Math.abs(vsAllocDiff) <= RECONCILE_TOLERANCE
    return {
      adjudicatedProvision,
      periodAmortTotal,
      allocTotal,
      vsAdjDiff,
      vsAllocDiff,
      matchedAdj,
      matchedAlloc,
    }
  })

  // ─── Row Management ────────────────────────────────────────────────────────

  /**
   * 从 I1-2 明细数据同步资产行。
   * Req 11.6: 摊销测算表显示每资产每月摊销额横向矩阵。
   *
   * 匹配逻辑：按 rowId 或 name 关联现有行，新增缺少的资产。
   */
  function syncFromDetail(assetParams: I1AssetParams[]): void {
    const targetRows = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair

    const existingMap = new Map<string, I1AmortizationRow>()
    for (const row of targetRows.value) {
      existingMap.set(row.rowId, row)
      // 也按 name 索引以便模糊匹配
      if (row.name) existingMap.set(`name:${row.name}`, row)
    }

    const newRows: I1AmortizationRow[] = []

    for (const param of assetParams) {
      // 尝试按 rowId 匹配
      let existing = existingMap.get(param.rowId)
      if (!existing) {
        // 按 name 匹配
        existing = existingMap.get(`name:${param.name}`)
      }

      if (existing) {
        // 更新参数但保留用户手工调整的字段（减值日期/账面月摊销等）
        existing.name = param.name
        existing.category = param.category ?? existing.category
        existing.cost = param.cost
        existing.salvage = param.cost * param.salvageRate
        existing.usefulLifeMonths = param.usefulLifeMonths
        existing.usefulLifeYears = param.usefulLifeMonths > 0
          ? Math.round((param.usefulLifeMonths / 12) * 100) / 100
          : existing.usefulLifeYears
        existing.accAmortBegin = param.accAmortBegin
        existing.bookAccAmortEnd = param.accAmortEnd ?? param.accAmortBegin
        if (param.acquisitionDate) existing.startDate = param.acquisitionDate
        if (param.amortProvision != null && param.amortProvision > 0) {
          existing.bookPeriodAmort = param.amortProvision
          existing.bookMonthly = Math.round((param.amortProvision / 12) * 100) / 100
        }
        if (amortBranch.value === 'withImpair') {
          existing.impairment = param.impairmentEnd
        } else {
          // I1-10 不含减值：同步时清零减值，避免误用含减值净值
          existing.impairment = 0
        }
        newRows.push(existing)
      } else {
        // 创建新行
        const salvage = param.cost * param.salvageRate
        const usefulLifeYears = param.usefulLifeMonths > 0
          ? Math.round((param.usefulLifeMonths / 12) * 100) / 100
          : 0
        const bookPeriodAmort = param.amortProvision != null && param.amortProvision > 0
          ? param.amortProvision
          : 0
        const bookMonthly = bookPeriodAmort > 0
          ? Math.round((bookPeriodAmort / 12) * 100) / 100
          : 0
        const row: I1AmortizationRow = {
          rowId: param.rowId || _genRowId(),
          category: param.category ?? '',
          name: param.name,
          cost: param.cost,
          salvage,
          accAmortBegin: param.accAmortBegin,
          bookAccAmortEnd: param.accAmortEnd ?? param.accAmortBegin,
          impairment: amortBranch.value === 'withImpair' ? param.impairmentEnd : 0,
          startDate: param.acquisitionDate ?? '',
          usefulLifeYears,
          bookMonthly,
          bookPeriodAmort,
          impairmentDate: '',
          usefulLifeMonths: param.usefulLifeMonths,
          usedMonths: 0,
          remainingMonths: param.usefulLifeMonths,
          beginNbv: 0,
          fullAmortDate: '',
          monthsAmortized: 0,
          monthsToImpairment: 0,
          periodMonths: 0,
          monthsBeforeImpairment: 0,
          monthsAfterImpairment: 0,
          preMonthly: 0,
          accAmortAtImpairment: 0,
          postMonthly: 0,
          monthlyDiff: 0,
          periodDiff: 0,
          calcAccAmort: 0,
          accAmortDiff: 0,
          impairmentMonth: 0,
          impairmentAmountAtMonth: 0,
          monthlyAmort: new Array(MATRIX_COLUMNS).fill(0),
          periodAmortization: 0,
          monthlyAmortAmount: 0,
        }
        newRows.push(row)
      }
    }

    targetRows.value = newRows
    recalcAll()
  }

  /**
   * 用 I1-7 寿命参数覆盖/补齐摊销测算表寿命（优先于仅认 I1-2）。
   * 寿命不确定项：usefulLifeMonths=0，不摊销。
   * 优先读 I1-7-indefinite-list.lifeParams，其次回退 I1-7-rows。
   */
  function syncFromUsefulLife(): { updated: number; message: string } {
    const byName = new Map<string, { usefulLifeMonths: number; isIndefinite: boolean }>()

    const absorbParams = (lifeParams: Array<{ name?: string; usefulLifeMonths?: number; isIndefinite?: boolean | string }>) => {
      for (const p of lifeParams) {
        const name = String(p.name || '').trim()
        if (!name) continue
        const indefinite = p.isIndefinite === true || p.isIndefinite === 'Y'
          || (!(Number(p.usefulLifeMonths) > 0) && p.isIndefinite !== false && p.isIndefinite !== 'N')
        byName.set(name, {
          usefulLifeMonths: indefinite ? 0 : Number(p.usefulLifeMonths) || 0,
          isIndefinite: indefinite,
        })
      }
    }

    const pubRaw = allResponses.value.get('I1-7-indefinite-list')?.remark
      ?? allResponses.value.get('I1-7-indefinite-list')?.conclusion
    if (pubRaw) {
      try {
        const parsed = typeof pubRaw === 'string' ? JSON.parse(pubRaw) : pubRaw
        if (Array.isArray(parsed?.lifeParams)) absorbParams(parsed.lifeParams)
      } catch { /* ignore */ }
    }

    // 回退：直接读 I1-7-rows
    if (!byName.size) {
      const lifeRaw = allResponses.value.get('I1-7-rows')?.remark
        ?? allResponses.value.get('I1-7-rows')?.conclusion
      let lifeRows: any[] = []
      if (Array.isArray(lifeRaw)) lifeRows = lifeRaw
      else if (typeof lifeRaw === 'string') {
        try { lifeRows = JSON.parse(lifeRaw) } catch { lifeRows = [] }
      }
      absorbParams(lifeRows.map((r) => ({
        name: r.name,
        usefulLifeMonths: Number(r.usefulLifeMonths) || 0,
        isIndefinite: r.isIndefinite === 'Y' || r.isIndefinite === true || !(Number(r.usefulLifeMonths) > 0),
      })))
    }

    if (!byName.size) {
      return { updated: 0, message: '未找到 I1-7 寿命数据（请先编制 I1-7 或发布不确定清单）' }
    }

    const targetRows = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair
    let updated = 0
    for (const row of targetRows.value) {
      const hit = byName.get(row.name)
      if (!hit) continue
      row.usefulLifeMonths = hit.usefulLifeMonths
      row.usefulLifeYears = hit.usefulLifeMonths > 0
        ? Math.round((hit.usefulLifeMonths / 12) * 100) / 100
        : 0
      row.remainingMonths = Math.max(0, hit.usefulLifeMonths - (row.usedMonths || 0))
      updated++
    }
    if (updated) recalcAll()
    return {
      updated,
      message: updated
        ? `已按 I1-7 更新 ${updated} 项寿命参数（不确定寿命不摊销）`
        : '无匹配资产名称可更新',
    }
  }

  /**
   * 更新单行字段值并重算矩阵。
   */
  function updateRowField(
    rowIndex: number,
    field: keyof I1AmortizationRow,
    value: number | string,
  ): void {
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    const row = rows[rowIndex]
    if (!row) return

    ;(row as any)[field] = value
    recalcRow(rowIndex)
  }

  /**
   * 设置减值发生月（仅 withImpair 分支，Req 11.5）。
   * 触发该行重算：减值月之后使用新基数。
   */
  function setImpairmentMonth(rowIndex: number, month: number, amount: number): void {
    if (amortBranch.value !== 'withImpair') return

    const row = rowsWithImpair.value[rowIndex]
    if (!row) return

    row.impairmentMonth = month
    row.impairmentAmountAtMonth = amount
    recalcRow(rowIndex)
  }

  /**
   * 手动添加一行。
   */
  function addRow(params: {
    name: string
    cost: number
    salvage: number
    usefulLifeMonths: number
    accAmortBegin?: number
    impairment?: number
    usedMonths?: number
    category?: string
    startDate?: string
    bookMonthly?: number
    bookPeriodAmort?: number
    impairmentDate?: string
  }): I1AmortizationRow {
    const usefulLifeMonths = params.usefulLifeMonths
    const bookPeriodAmort = params.bookPeriodAmort
      ?? (params.bookMonthly != null ? params.bookMonthly * 12 : 0)
    const row: I1AmortizationRow = {
      rowId: _genRowId(),
      category: params.category ?? '',
      name: params.name,
      cost: params.cost,
      salvage: params.salvage,
      accAmortBegin: params.accAmortBegin ?? 0,
      bookAccAmortEnd: params.accAmortBegin ?? 0,
      impairment: params.impairment ?? 0,
      startDate: params.startDate ?? '',
      usefulLifeYears: usefulLifeMonths > 0 ? Math.round((usefulLifeMonths / 12) * 100) / 100 : 0,
      bookMonthly: params.bookMonthly ?? (bookPeriodAmort > 0 ? bookPeriodAmort / 12 : 0),
      bookPeriodAmort,
      impairmentDate: params.impairmentDate ?? '',
      usefulLifeMonths,
      usedMonths: params.usedMonths ?? 0,
      remainingMonths: Math.max(0, usefulLifeMonths - (params.usedMonths ?? 0)),
      beginNbv: 0,
      fullAmortDate: '',
      monthsAmortized: 0,
      monthsToImpairment: 0,
      periodMonths: 0,
      monthsBeforeImpairment: 0,
      monthsAfterImpairment: 0,
      preMonthly: 0,
      accAmortAtImpairment: 0,
      postMonthly: 0,
      monthlyDiff: 0,
      periodDiff: 0,
      calcAccAmort: 0,
      accAmortDiff: 0,
      impairmentMonth: 0,
      impairmentAmountAtMonth: 0,
      monthlyAmort: new Array(MATRIX_COLUMNS).fill(0),
      periodAmortization: 0,
      monthlyAmortAmount: 0,
    }

    const targetRows = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair
    targetRows.value.push(row)

    const idx = targetRows.value.length - 1
    recalcRow(idx)

    return row
  }

  /**
   * 删除行。
   */
  function removeRow(rowIndex: number): void {
    const targetRows = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair
    if (rowIndex < 0 || rowIndex >= targetRows.value.length) return
    targetRows.value.splice(rowIndex, 1)
    _persist()
  }

  /**
   * 从 I1-12 减值测试回写 I1-11（按名称匹配）。
   * - impairment ← ⑦ alreadyProvided（期末已计提）
   * - 若 ⑧ supplement>0，减值日默认取截止日（本年计提假设）
   */
  function syncFromImpairment(
    params: Array<{
      rowId?: string
      name: string
      category?: string
      cost?: number
      accAmort?: number
      alreadyProvided: number
      supplement?: number
    }>,
    opts?: { defaultImpairmentDate?: string; createMissing?: boolean },
  ): { linked: number; added: number; skipped: number; message: string } {
    const prevBranch = amortBranch.value
    amortBranch.value = 'withImpair'

    const byName = new Map<string, I1AmortizationRow>()
    for (const row of rowsWithImpair.value) {
      if (row.name) byName.set(row.name.trim(), row)
    }

    let linked = 0
    let added = 0
    let skipped = 0
    const impairDateDefault = opts?.defaultImpairmentDate || periodEnd.value || ''

    for (const p of params) {
      const name = (p.name || '').trim()
      if (!name) { skipped++; continue }
      const impairAmt = Number(p.alreadyProvided) || 0
      if (impairAmt <= 0 && !(Number(p.supplement) > 0)) { skipped++; continue }

      let row = byName.get(name)
      if (!row) {
        if (!opts?.createMissing) { skipped++; continue }
        row = {
          rowId: p.rowId || _genRowId(),
          category: p.category ?? '',
          name,
          cost: Number(p.cost) || 0,
          salvage: 0,
          accAmortBegin: Number(p.accAmort) || 0,
          bookAccAmortEnd: Number(p.accAmort) || 0,
          impairment: impairAmt,
          startDate: '',
          usefulLifeYears: 0,
          bookMonthly: 0,
          bookPeriodAmort: 0,
          impairmentDate: Number(p.supplement) > 0 ? impairDateDefault : '',
          usefulLifeMonths: 0,
          usedMonths: 0,
          remainingMonths: 0,
          beginNbv: 0,
          fullAmortDate: '',
          monthsAmortized: 0,
          monthsToImpairment: 0,
          periodMonths: 0,
          monthsBeforeImpairment: 0,
          monthsAfterImpairment: 0,
          preMonthly: 0,
          accAmortAtImpairment: 0,
          postMonthly: 0,
          monthlyDiff: 0,
          periodDiff: 0,
          calcAccAmort: 0,
          accAmortDiff: 0,
          impairmentMonth: 0,
          impairmentAmountAtMonth: Number(p.supplement) || 0,
          monthlyAmort: new Array(MATRIX_COLUMNS).fill(0),
          periodAmortization: 0,
          monthlyAmortAmount: 0,
        }
        rowsWithImpair.value.push(row)
        byName.set(name, row)
        added++
      } else {
        row.impairment = impairAmt
        if (p.category) row.category = p.category
        if (p.cost != null && p.cost > 0) row.cost = p.cost
        if (p.accAmort != null) {
          row.accAmortBegin = p.accAmort
          row.bookAccAmortEnd = p.accAmort
        }
        if (Number(p.supplement) > 0) {
          row.impairmentAmountAtMonth = Number(p.supplement) || 0
          if (!row.impairmentDate) row.impairmentDate = impairDateDefault
        }
        linked++
      }
    }

    recalcAll()
    amortBranch.value = prevBranch
    if (prevBranch !== 'withImpair') {
      options?.onSave?.(ITEM_ID_WITH_IMPAIR, rowsWithImpair.value)
    }

    return {
      linked,
      added,
      skipped,
      message: `I1-12→I1-11：更新 ${linked} 行${added ? `，新增 ${added} 行` : ''}${skipped ? `，跳过 ${skipped}` : ''}`,
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const itemId = currentItemId.value
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    options?.onSave?.(itemId, rows)
    const periodTotal = rows.reduce((s, r) => s + (r.periodAmortization || 0), 0)
    const totalKey = amortBranch.value === 'noImpair' ? ITEM_ID_PERIOD_TOTAL_NO : ITEM_ID_PERIOD_TOTAL_WITH
    options?.onSave?.(totalKey, periodTotal)
  }

  function setPeriod(begin: string, end: string): void {
    periodBegin.value = begin || ''
    periodEnd.value = end || ''
    const payload = {
      periodBegin: periodBegin.value,
      periodEnd: periodEnd.value,
    }
    // 双写：新键为主，旧键兼容已打开的 I1-11 / 减值联动
    options?.onSave?.(ITEM_ID_PERIOD, payload)
    options?.onSave?.(ITEM_ID_PERIOD_LEGACY, payload)
    // I1-10 / I1-11 均依赖期间推算本期月数
    recalcAll()
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  /** 导入行数据（覆盖当前分支） */
  function importRows(importedRows: Partial<I1AmortizationRow>[]): void {
    const targetRows = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair
    targetRows.value = importedRows.map(_normalizeRow)
    recalcAll()
  }

  /** 导出当前分支行数据 */
  function exportRows(): I1AmortizationRow[] {
    return [...currentRows.value]
  }

  const EXPORT_HEADERS_NO_IMPAIR = [
    '类别', '明细项目', '原值', '累计摊销期初', '账面累计摊销期末', '账面本期摊销',
    '开始使用日期', '使用期限(年)', '残值',
  ] as const

  const EXPORT_HEADERS_WITH_IMPAIR = [
    '类别', '明细项目', '原值', '账面累计摊销', '减值准备', '计提减值准备日期',
    '开始使用日期', '使用期限(年)', '账面月摊销额', '残值',
  ] as const

  /** 客户端导出对齐源表列的 xlsx（模板/数据） */
  async function exportXlsx(kind: 'template' | 'data' = 'data'): Promise<void> {
    const withImpair = amortBranch.value === 'withImpair'
    const headers = [...(withImpair ? EXPORT_HEADERS_WITH_IMPAIR : EXPORT_HEADERS_NO_IMPAIR)]
    const rows = currentRows.value
    const dataRows = kind === 'template'
      ? []
      : rows.map((row) => (withImpair
        ? {
            类别: row.category || '',
            明细项目: row.name || '',
            原值: row.cost || 0,
            账面累计摊销: row.bookAccAmortEnd || row.accAmortBegin || 0,
            减值准备: row.impairment || 0,
            计提减值准备日期: row.impairmentDate || '',
            开始使用日期: row.startDate || '',
            '使用期限(年)': row.usefulLifeYears || 0,
            账面月摊销额: row.bookMonthly || 0,
            残值: row.salvage || 0,
          }
        : {
            类别: row.category || '',
            明细项目: row.name || '',
            原值: row.cost || 0,
            累计摊销期初: row.accAmortBegin || 0,
            账面累计摊销期末: row.bookAccAmortEnd || 0,
            账面本期摊销: row.bookPeriodAmort || 0,
            开始使用日期: row.startDate || '',
            '使用期限(年)': row.usefulLifeYears || 0,
            残值: row.salvage || 0,
          }))
    // 走 useExcelIO 单一入口（B3 批）。模板态 = 只有表头行；数据态 = 表头 + 按 headers
    // 顺序取值 —— json_to_sheet 与 aoa_to_sheet 对缺失字段同样跳过该单元格，故逐格等价。
    const sheetName = withImpair ? 'I1-11含减值' : 'I1-10不含减值'
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: sheetName,
          rows: kind === 'template'
            ? [headers]
            : [headers, ...dataRows.map((r) => headers.map((h) => (r as any)[h]))],
        },
      ],
      fileName: `${sheetName}_${kind === 'template' ? '模板' : '数据'}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
  }

  /** 客户端导入对齐源表列的 xlsx */
  async function importXlsx(file: File, replace = true): Promise<{ imported: number }> {
    // 走 useExcelIO 低层入口（B3 批）。原实现 = read(buffer,{type:'array',cellDates:false})
    // + sheet_to_json(sheet,{defval:''}) + 取第一个 sheet。
    // 🔴 cellDates 与 defval 必须显式透传：前者决定日期是 Date 还是序列号，
    // 后者决定空单元格填 '' 还是被跳过（下游用 ?? / || 取值时两者行为不同）。
    const { rows: rawRows } = await readSheetObjects<Record<string, any>>(file, {
      cellDates: false,
      defval: '',
    })
    const withImpair = amortBranch.value === 'withImpair'

    const mapped: Partial<I1AmortizationRow>[] = rawRows.map((r) => {
      const name = String(r['明细项目'] ?? r['资产名称'] ?? r.name ?? '').trim()
      const usefulLifeYears = _getNum(r['使用期限(年)'] ?? r['使用年限'] ?? r.usefulLifeYears)
      const usefulLifeMonths = usefulLifeYears > 0 ? Math.round(usefulLifeYears * 12) : 0
      if (withImpair) {
        return {
          category: String(r['类别'] ?? r.category ?? ''),
          name,
          cost: _getNum(r['原值'] ?? r.cost),
          bookAccAmortEnd: _getNum(r['账面累计摊销'] ?? r.bookAccAmortEnd),
          accAmortBegin: _getNum(r['账面累计摊销'] ?? r['累计摊销期初'] ?? r.accAmortBegin),
          impairment: _getNum(r['减值准备'] ?? r.impairment),
          impairmentDate: String(r['计提减值准备日期'] ?? r['减值日期'] ?? ''),
          startDate: String(r['开始使用日期'] ?? r.startDate ?? ''),
          usefulLifeYears,
          usefulLifeMonths,
          bookMonthly: _getNum(r['账面月摊销额'] ?? r.bookMonthly),
          salvage: _getNum(r['残值'] ?? r.salvage),
        }
      }
      return {
        category: String(r['类别'] ?? r.category ?? ''),
        name,
        cost: _getNum(r['原值'] ?? r.cost),
        accAmortBegin: _getNum(r['累计摊销期初'] ?? r.accAmortBegin),
        bookAccAmortEnd: _getNum(r['账面累计摊销期末'] ?? r.bookAccAmortEnd),
        bookPeriodAmort: _getNum(r['账面本期摊销'] ?? r.bookPeriodAmort),
        startDate: String(r['开始使用日期'] ?? r.startDate ?? ''),
        usefulLifeYears,
        usefulLifeMonths,
        salvage: _getNum(r['残值'] ?? r.salvage),
      }
    }).filter((r) => r.name)

    if (replace) {
      importRows(mapped)
    } else {
      const target = amortBranch.value === 'noImpair' ? rowsNoImpair : rowsWithImpair
      for (const partial of mapped) {
        target.value.push(_normalizeRow(partial))
      }
      recalcAll()
    }
    return { imported: mapped.length }
  }

  // ─── Init: watch allResponses 加载数据 ─────────────────────────────────────

  watch(allResponses, () => {
    _loadBranch()
    _loadPeriod()
    _loadRows()
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // ── State ──
    amortBranch,
    rowsNoImpair,
    rowsWithImpair,
    periodBegin,
    periodEnd,

    // ── Derived ──
    currentRows,
    currentItemId,

    // ── Computed ──
    summaryRow,
    assetPeriodTotals,
    amortReconcile,

    // ── Constants ──
    AMORT_BRANCH_OPTIONS,
    MATRIX_COLUMNS,

    // ── Actions — Branch ──
    switchBranch,

    // ── Actions — Calculation ──
    recalcAll,
    recalcRow,
    setPeriod,

    // ── Actions — Row management ──
    syncFromDetail,
    syncFromUsefulLife,
    syncFromImpairment,
    updateRowField,
    setImpairmentMonth,
    addRow,
    removeRow,

    // ── Actions — Import/Export ──
    importRows,
    exportRows,
    exportXlsx,
    importXlsx,
  }
}

export default useI1Amortization
