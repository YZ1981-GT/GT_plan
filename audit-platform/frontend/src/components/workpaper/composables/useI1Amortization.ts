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
import type { ChecklistItem } from './useI1FormData'
import {
  calcStraightLineAmort,
  calcRemainingLifeAmort,
  calcAmortWithImpairment,
} from './useI1AmortizationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 摊销分支类型 */
export type AmortBranch = 'noImpair' | 'withImpair'

/** 分支选择器选项（供 el-segmented 使用） */
export interface AmortBranchOption {
  label: string
  value: AmortBranch
}

/** 摊销矩阵行：每资产 + 28列月摊销 */
export interface I1AmortizationRow {
  rowId: string
  /** 资产名称（来自 I1-2） */
  name: string
  /** 原值 */
  cost: number
  /** 预计残值 */
  salvage: number
  /** 累计摊销期初 */
  accAmortBegin: number
  /** 减值准备（仅 withImpair 分支使用） */
  impairment: number
  /** 使用寿命总月数 */
  usefulLifeMonths: number
  /** 已使用月数 */
  usedMonths: number
  /** 剩余月数 = usefulLifeMonths - usedMonths */
  remainingMonths: number
  /** 减值发生月（1-based 月索引，0=无减值）：用于 withImpair 分支重置基数 */
  impairmentMonth: number
  /** 减值发生后新增的减值金额 */
  impairmentAmountAtMonth: number
  /** 月摊销额矩阵（最多28列，对应审计期间月份） */
  monthlyAmort: number[]
  /** 本期摊销合计 = sum(monthlyAmort) */
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

/** 从 I1-2 提取的资产参数（用于初始化/同步行） */
export interface I1AssetParams {
  rowId: string
  name: string
  cost: number
  salvageRate: number
  usefulLifeMonths: number
  accAmortBegin: number
  impairmentEnd: number
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

    return {
      rowId: raw.rowId ?? _genRowId(),
      name: raw.name ?? '',
      cost: _getNum(raw.cost),
      salvage: _getNum(raw.salvage),
      accAmortBegin: _getNum(raw.accAmortBegin),
      impairment: _getNum(raw.impairment),
      usefulLifeMonths: _getNum(raw.usefulLifeMonths),
      usedMonths: _getNum(raw.usedMonths),
      remainingMonths: _getNum(raw.remainingMonths),
      impairmentMonth: _getNum(raw.impairmentMonth),
      impairmentAmountAtMonth: _getNum(raw.impairmentAmountAtMonth),
      monthlyAmort,
      periodAmortization,
      monthlyAmortAmount: _getNum(raw.monthlyAmortAmount),
    }
  }

  // ─── Branch Switch (Req 11.1) ──────────────────────────────────────────────

  /**
   * 切换摊销分支。
   * Req 11.1: el-segmented切换 "不含减值（I1-10）" / "含减值（I1-11）"
   */
  function switchBranch(branch: AmortBranch): void {
    amortBranch.value = branch
    options?.onSave?.(ITEM_ID_BRANCH, branch)
  }

  // ─── Amortization Matrix Calculation ───────────────────────────────────────

  /**
   * 计算单行摊销矩阵（不含减值版本 — I1-10）。
   * Req 11.4: 月摊销额 = (原值 - 残值 - 累计摊销 - 减值准备) / 剩余月数
   * I1-10 版本 impairment = 0。
   *
   * 从 usedMonths 开始，按月递增 remainingMonths，逐月填充摊销额：
   * - 每月摊销额 = calcRemainingLifeAmort(cost, salvage, accAmort累积, 0, remainingMonths递减)
   * - 但剩余年限法（不含减值）月摊销恒定，因为分母和分子按同比例变化
   */
  function _calcMatrixNoImpair(row: I1AmortizationRow): void {
    const { cost, salvage, accAmortBegin, remainingMonths } = row

    if (remainingMonths <= 0 || cost <= 0) {
      row.monthlyAmort = new Array(MATRIX_COLUMNS).fill(0)
      row.periodAmortization = 0
      row.monthlyAmortAmount = 0
      return
    }

    // I1-10 不含减值：impairment = 0，使用 calcRemainingLifeAmort
    const monthlyAmount = calcRemainingLifeAmort(cost, salvage, accAmortBegin, 0, remainingMonths)
    row.monthlyAmortAmount = monthlyAmount

    // 填充月摊销矩阵：最多填 remainingMonths 个月，不超过 MATRIX_COLUMNS
    const monthsToFill = Math.min(remainingMonths, MATRIX_COLUMNS)
    const matrix: number[] = []
    for (let i = 0; i < MATRIX_COLUMNS; i++) {
      matrix.push(i < monthsToFill ? monthlyAmount : 0)
    }

    row.monthlyAmort = matrix
    row.periodAmortization = matrix.reduce((sum, v) => sum + v, 0)
  }

  /**
   * 计算单行摊销矩阵（含减值版本 — I1-11）。
   * Req 11.5: 含减值版本在减值发生月重新计算剩余摊销基数。
   *
   * 逻辑：
   * - 减值发生前：月摊销 = calcRemainingLifeAmort(cost, salvage, accAmort, 0, remaining)
   * - 减值发生月：重新计算基数 = calcAmortWithImpairment(cost, salvage, accAmortAtMonth, impairment, remainingAfter)
   * - 减值发生后：使用新月摊销额
   */
  function _calcMatrixWithImpair(row: I1AmortizationRow): void {
    const {
      cost, salvage, accAmortBegin, impairment,
      remainingMonths, impairmentMonth, impairmentAmountAtMonth,
    } = row

    if (remainingMonths <= 0 || cost <= 0) {
      row.monthlyAmort = new Array(MATRIX_COLUMNS).fill(0)
      row.periodAmortization = 0
      row.monthlyAmortAmount = 0
      return
    }

    const matrix: number[] = []
    let accAmortCumulative = accAmortBegin
    let currentImpairment = impairment - impairmentAmountAtMonth  // 减值发生前的已有减值
    let currentRemaining = remainingMonths
    let monthlyAmount = 0

    // 如果无减值月（impairmentMonth=0），退化为不含减值逻辑
    const effectiveImpairMonth = impairmentMonth > 0 ? impairmentMonth : MATRIX_COLUMNS + 1

    for (let m = 0; m < MATRIX_COLUMNS; m++) {
      if (currentRemaining <= 0) {
        matrix.push(0)
        continue
      }

      if (m + 1 === effectiveImpairMonth) {
        // 减值发生月：用减值前已累积的摊销重新计算基数
        currentImpairment += impairmentAmountAtMonth
        monthlyAmount = calcAmortWithImpairment(
          cost, salvage, accAmortCumulative, currentImpairment, currentRemaining,
        )
      } else if (m + 1 < effectiveImpairMonth) {
        // 减值发生前
        monthlyAmount = calcRemainingLifeAmort(
          cost, salvage, accAmortCumulative, currentImpairment, currentRemaining,
        )
      }
      // 减值发生后：使用上一步计算的 monthlyAmount 不变（已在减值月重算）

      matrix.push(monthlyAmount)
      accAmortCumulative += monthlyAmount
      currentRemaining--
    }

    row.monthlyAmort = matrix
    row.monthlyAmortAmount = monthlyAmount
    row.periodAmortization = matrix.reduce((sum, v) => sum + v, 0)
  }

  /**
   * 重算当前分支所有行的摊销矩阵。
   */
  function recalcAll(): void {
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    const calcFn = amortBranch.value === 'noImpair' ? _calcMatrixNoImpair : _calcMatrixWithImpair

    for (const row of rows) {
      // 确保 remainingMonths 正确
      row.remainingMonths = Math.max(0, row.usefulLifeMonths - row.usedMonths)
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

    row.remainingMonths = Math.max(0, row.usefulLifeMonths - row.usedMonths)

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
        // 更新参数但保留用户手工调整的字段
        existing.name = param.name
        existing.cost = param.cost
        existing.salvage = param.cost * param.salvageRate
        existing.usefulLifeMonths = param.usefulLifeMonths
        existing.accAmortBegin = param.accAmortBegin
        if (amortBranch.value === 'withImpair') {
          existing.impairment = param.impairmentEnd
        }
        newRows.push(existing)
      } else {
        // 创建新行
        const salvage = param.cost * param.salvageRate
        const row: I1AmortizationRow = {
          rowId: param.rowId || _genRowId(),
          name: param.name,
          cost: param.cost,
          salvage,
          accAmortBegin: param.accAmortBegin,
          impairment: amortBranch.value === 'withImpair' ? param.impairmentEnd : 0,
          usefulLifeMonths: param.usefulLifeMonths,
          usedMonths: 0,
          remainingMonths: param.usefulLifeMonths,
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
  }): I1AmortizationRow {
    const row: I1AmortizationRow = {
      rowId: _genRowId(),
      name: params.name,
      cost: params.cost,
      salvage: params.salvage,
      accAmortBegin: params.accAmortBegin ?? 0,
      impairment: params.impairment ?? 0,
      usefulLifeMonths: params.usefulLifeMonths,
      usedMonths: params.usedMonths ?? 0,
      remainingMonths: Math.max(0, params.usefulLifeMonths - (params.usedMonths ?? 0)),
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

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const itemId = currentItemId.value
    const rows = amortBranch.value === 'noImpair' ? rowsNoImpair.value : rowsWithImpair.value
    options?.onSave?.(itemId, rows)
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

  // ─── Init: watch allResponses 加载数据 ─────────────────────────────────────

  watch(allResponses, () => {
    _loadBranch()
    _loadRows()
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // ── State ──
    amortBranch,
    rowsNoImpair,
    rowsWithImpair,

    // ── Derived ──
    currentRows,
    currentItemId,

    // ── Computed ──
    summaryRow,
    assetPeriodTotals,

    // ── Constants ──
    AMORT_BRANCH_OPTIONS,
    MATRIX_COLUMNS,

    // ── Actions — Branch ──
    switchBranch,

    // ── Actions — Calculation ──
    recalcAll,
    recalcRow,

    // ── Actions — Row management ──
    syncFromDetail,
    updateRowField,
    setImpairmentMonth,
    addRow,
    removeRow,

    // ── Actions — Import/Export ──
    importRows,
    exportRows,
  }
}

export default useI1Amortization
