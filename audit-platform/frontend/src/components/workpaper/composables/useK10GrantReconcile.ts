/**
 * useK10GrantReconcile — K10-4 政府补助核对表逻辑
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 3.4
 * Requirements: 4.1-4.5
 *
 * 职责：
 * - 动态行管理（一行=一个补助项目）
 * - 列结构：补助项目/期间/直接冲减成本/直接计入其他收益/直接计入营业外收入/
 *           新增递延/期初递延余额/摊销冲减成本/摊销转其他收益/摊销转营业外收入/返还/其他转出/期末递延余额
 * - 期末公式：期末 = 期初 + 新增 - 摊销(成本) - 摊销(其他收益) - 摊销(营业外) - 返还 - 其他
 * - 使用 calcTotalRecognized / isConsistentWithK7 from useK10GrantReconcileEngine
 * - K7一致性检查：递延分摊合计 vs K7(2401)本期分摊
 *
 * Item IDs: "K10-4-rows", "K10-4-k7-consistency"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useK10FormulaEngine'
import { calcTotalRecognized, isConsistentWithK7 } from './useK10GrantReconcileEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K10GrantRow {
  rowKey: string
  /** 补助项目名称 */
  projectName: string
  /** 补助期间 */
  period: string
  /** 直接冲减成本 */
  directReduceCost: number
  /** 直接计入其他收益 */
  directToOtherIncome: number
  /** 直接计入营业外收入 */
  directToNonOpIncome: number
  /** 新增递延收益 */
  newDeferred: number
  /** 期初递延余额 */
  openingDeferred: number
  /** 摊销冲减成本 */
  amortReduceCost: number
  /** 摊销转其他收益 */
  amortToOtherIncome: number
  /** 摊销转营业外收入 */
  amortToNonOpIncome: number
  /** 返还 */
  refund: number
  /** 其他转出 */
  otherTransferOut: number
  /** 期末递延余额（公式：期初+新增-摊销成本-摊销其他收益-摊销营业外-返还-其他） */
  closingDeferred: number
  /** 可编辑标记 */
  isEditable: boolean
}

export interface K10GrantTotals {
  directReduceCost: number
  directToOtherIncome: number
  directToNonOpIncome: number
  newDeferred: number
  openingDeferred: number
  amortReduceCost: number
  amortToOtherIncome: number
  amortToNonOpIncome: number
  refund: number
  otherTransferOut: number
  closingDeferred: number
  /** 合计计入其他收益 = 直接计入 + 递延摊销计入 */
  totalRecognizedOtherIncome: number
}

export interface K10K7Consistency {
  /** K10-4递延分摊计入合计 */
  deferredAmortInK10: number
  /** K7递延收益(2401)本期分摊 */
  amortInK7: number
  /** 差异 */
  diff: number
  /** 是否一致 */
  isConsistent: boolean
}

export interface UseK10GrantReconcileParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K10-4'
const ROWS_KEY = `${ITEM_PREFIX}-rows`

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK10GrantReconcile(params: UseK10GrantReconcileParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K10GrantRow[]>([])
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
    } else {
      rows.value = []
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): K10GrantRow {
    const openingDeferred = parseNum(raw.openingDeferred)
    const newDeferred = parseNum(raw.newDeferred)
    const amortReduceCost = parseNum(raw.amortReduceCost)
    const amortToOtherIncome = parseNum(raw.amortToOtherIncome)
    const amortToNonOpIncome = parseNum(raw.amortToNonOpIncome)
    const refund = parseNum(raw.refund)
    const otherTransferOut = parseNum(raw.otherTransferOut)
    const closingDeferred = _calcClosingDeferred(
      openingDeferred, newDeferred, amortReduceCost, amortToOtherIncome, amortToNonOpIncome, refund, otherTransferOut
    )

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      period: raw.period ?? '',
      directReduceCost: parseNum(raw.directReduceCost),
      directToOtherIncome: parseNum(raw.directToOtherIncome),
      directToNonOpIncome: parseNum(raw.directToNonOpIncome),
      newDeferred,
      openingDeferred,
      amortReduceCost,
      amortToOtherIncome,
      amortToNonOpIncome,
      refund,
      otherTransferOut,
      closingDeferred,
      isEditable: raw.isEditable ?? true,
    }
  }

  /** 期末递延余额 = 期初 + 新增 - 摊销成本 - 摊销其他收益 - 摊销营业外 - 返还 - 其他转出 */
  function _calcClosingDeferred(
    opening: number, newDef: number,
    amortCost: number, amortOI: number, amortNonOp: number,
    refund: number, other: number
  ): number {
    return opening + newDef - amortCost - amortOI - amortNonOp - refund - other
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K10GrantRow[]> = computed(() => {
    return rows.value.map((row) => {
      const closingDeferred = _calcClosingDeferred(
        row.openingDeferred, row.newDeferred,
        row.amortReduceCost, row.amortToOtherIncome, row.amortToNonOpIncome,
        row.refund, row.otherTransferOut
      )
      return { ...row, closingDeferred }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totals: ComputedRef<K10GrantTotals> = computed(() => {
    const detail = computedRows.value
    const directReduceCost = calcSubtotal(detail.map(r => r.directReduceCost))
    const directToOtherIncome = calcSubtotal(detail.map(r => r.directToOtherIncome))
    const directToNonOpIncome = calcSubtotal(detail.map(r => r.directToNonOpIncome))
    const newDeferred = calcSubtotal(detail.map(r => r.newDeferred))
    const openingDeferred = calcSubtotal(detail.map(r => r.openingDeferred))
    const amortReduceCost = calcSubtotal(detail.map(r => r.amortReduceCost))
    const amortToOtherIncome = calcSubtotal(detail.map(r => r.amortToOtherIncome))
    const amortToNonOpIncome = calcSubtotal(detail.map(r => r.amortToNonOpIncome))
    const refund = calcSubtotal(detail.map(r => r.refund))
    const otherTransferOut = calcSubtotal(detail.map(r => r.otherTransferOut))
    const closingDeferred = _calcClosingDeferred(
      openingDeferred, newDeferred, amortReduceCost, amortToOtherIncome, amortToNonOpIncome, refund, otherTransferOut
    )
    // 合计计入其他收益 = 直接计入 + 递延摊销计入其他收益
    const totalRecognizedOtherIncome = calcTotalRecognized(directToOtherIncome, amortToOtherIncome)

    return {
      directReduceCost, directToOtherIncome, directToNonOpIncome,
      newDeferred, openingDeferred,
      amortReduceCost, amortToOtherIncome, amortToNonOpIncome,
      refund, otherTransferOut, closingDeferred,
      totalRecognizedOtherIncome,
    }
  })

  // ─── K7一致性校验 ──────────────────────────────────────────────────────────

  const k7Consistency: ComputedRef<K10K7Consistency> = computed(() => {
    // K10-4中递延分摊合计（摊销转其他收益合计）
    const deferredAmortInK10 = totals.value.amortToOtherIncome
    // K7递延收益本期分摊（从allResponses中读取K7已存数据）
    const k7Raw = allResponses.value.get('K7-deferred-amort-total')
    const amortInK7 = parseNum(k7Raw?.remark ?? k7Raw?.conclusion ?? 0)
    const diff = deferredAmortInK10 - amortInK7
    const isConsistent = isConsistentWithK7(deferredAmortInK10, amortInK7)
    return { deferredAmortInK10, amortInK7, diff, isConsistent }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K10GrantRow): void {
    row.closingDeferred = _calcClosingDeferred(
      row.openingDeferred, row.newDeferred,
      row.amortReduceCost, row.amortToOtherIncome, row.amortToNonOpIncome,
      row.refund, row.otherTransferOut
    )
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      period: '',
      directReduceCost: 0,
      directToOtherIncome: 0,
      directToNonOpIncome: 0,
      newDeferred: 0,
      openingDeferred: 0,
      amortReduceCost: 0,
      amortToOtherIncome: 0,
      amortToNonOpIncome: 0,
      refund: 0,
      otherTransferOut: 0,
      closingDeferred: 0,
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 存K7一致性状态供CrossSheet使用
    onSave(`${ITEM_PREFIX}-k7-consistency`, k7Consistency.value.isConsistent)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totals,
    k7Consistency,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    initFromResponses,
  }
}

export default useK10GrantReconcile
